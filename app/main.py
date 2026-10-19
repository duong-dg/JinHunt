import hashlib
import hmac
import io
import math
import os
import re
import secrets
import time
import unicodedata
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import User, Token, Case, Solve, Comment, Attempt, Like, Notification, AnswerAlias, ContentAttestation
from .migrations import upgrade
from .legal import ConsentInput, VERSION as LEGAL_VERSION, age, latest_consent, record_consent, start_guardian, build_router

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app):
    upgrade(engine)
    yield

app = FastAPI(title="JinHunt API", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
@app.get("/uploads/{filename}",include_in_schema=False)
def uploaded_image(filename: str, db: Session = Depends(get_db)):
    match = re.fullmatch(r"(?:avatar-)?([0-9]+)-[a-f0-9]{32}\.jpg",filename)
    owner = db.get(User,int(match.group(1))) if match else None
    if not owner or owner.account_status != "active" or not (UPLOAD_DIR/filename).is_file():
        raise HTTPException(404,"Không tìm thấy ảnh.")
    return FileResponse(UPLOAD_DIR/filename,media_type="image/jpeg",headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

def normalize(value):
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", value))

def public_user(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name or user.username,
            "bio": user.bio or "", "avatar_url": user.avatar_url,
            "xp": user.total_xp, "level": user.total_xp // 200 + 1}

def private_user(user, db=None):
    return {**public_user(user), "email": user.email, "phone": user.phone,
            "contact_verified": False, "guardian_managed":bool(user.guardian_managed),
            "needs_legal_consent":bool(db is not None and (not user.player_birth_date or not latest_consent(db,user))),
            "legal_version":LEGAL_VERSION}

def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    raw = authorization.removeprefix("Bearer ")
    token = db.get(Token, hashlib.sha256(raw.encode()).hexdigest())
    if not authorization.startswith("Bearer ") or not token or token.expires_at < time.time():
        raise HTTPException(401, "Vui lòng đăng nhập lại.")
    user = db.get(User, token.user_id)
    if user.account_status != "active":
        raise HTTPException(403,"Tài khoản chưa được kích hoạt hoặc đã dừng. Hãy kiểm tra xác nhận người đại diện hoặc liên hệ hỗ trợ.")
    return user

def participant(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.player_birth_date or not latest_consent(db,user):
        raise HTTPException(403,"Cần xác nhận độ tuổi, Điều khoản sử dụng và Chính sách quyền riêng tư trong tài khoản trước khi tham gia.")
    return user

def optional_user(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    return current_user(authorization, db) if authorization else None

def notify(db, case, actor, kind, source_id=None):
    if case.creator_id == actor.id:
        return
    key = f"comment:{source_id}" if kind == "comment" else f"{kind}:{case.id}:{actor.id}"
    existing = db.scalar(select(Notification).where(Notification.event_key == key))
    # Retries and repeated unlike/like cycles do not flood the inbox.
    if not existing:
        try:
            with db.begin_nested():
                db.add(Notification(recipient_id=case.creator_id, actor_id=actor.id, case_id=case.id, kind=kind, event_key=key))
                db.flush()
        except IntegrityError:
            pass

def answer_matches(db, case, text):
    normalized = normalize(text)
    answers = [case.answer, *db.scalars(select(AnswerAlias.answer).where(AnswerAlias.case_id == case.id))]
    hidden = correct = False
    for answer in answers:
        phrase = normalize(answer)
        for match in re.finditer(r"(?<!\S)" + re.escape(phrase) + r"(?!\S)", normalized):
            hidden = True
            prefix = normalized[:match.start()].strip()
            if not re.search(r"(?:khong phai|khong la|chang phai|chua chac|khong chac)(?: \w+){0,3}$", prefix):
                correct = True
    return hidden, correct

def limit_attempt(db, user, case_id):
    recent = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == user.id, Attempt.created_at > time.time() - 60))
    if recent >= 10:
        raise HTTPException(429, "Bạn đã gửi 10 lượt trong một phút. Hãy chờ một chút.")
    db.add(Attempt(user_id=user.id, case_id=case_id, created_at=time.time()))

def award_solve(db, case, user):
    if case.creator_id == user.id:
        return "author", 0
    if db.scalar(select(Solve).where(Solve.user_id == user.id, Solve.case_id == case.id)):
        return "already_solved", 0
    try:
        with db.begin_nested():
            db.add(Solve(user_id=user.id, case_id=case.id))
            db.flush()
            db.execute(update(User).where(User.id == user.id).values(total_xp=User.total_xp + case.reward_xp))
    except IntegrityError:
        return "already_solved", 0
    notify(db, case, user, "solve")
    return "correct", case.reward_xp

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=254, description="Username, email hoặc số điện thoại")
    password: str = Field(min_length=8, max_length=128)

def clean_email(value):
    value = value.strip().lower() if value else None
    if value and (len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value)):
        raise ValueError("Email không hợp lệ.")
    return value or None

def clean_phone(value):
    value = re.sub(r"[\s().-]", "", value or "")
    if value.startswith("0"):
        value = "+84" + value[1:]
    if value and not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise ValueError("Số điện thoại cần mã quốc gia, ví dụ +84901234567 hoặc 0901234567.")
    return value or None

class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        return clean_email(value)

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, value):
        return clean_phone(value)

    @field_validator("display_name", "bio")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if value else None

class Registration(ProfileUpdate, ConsentInput):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,30}$")
    password: str | None = Field(default=None,min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_contact(self):
        if age(self.player_birth_date)>=18 and not self.email and not self.phone:
            raise ValueError("Cần cung cấp email hoặc số điện thoại.")
        if age(self.player_birth_date)>=18 and not self.password:
            raise ValueError("Người từ đủ 18 tuổi cần đặt mật khẩu.")
        return self

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"

def session_response(user, db):
    raw = secrets.token_urlsafe(32)
    db.add(Token(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires_at=time.time() + 86400 * 7))
    db.commit()
    return {"token": raw, "user": private_user(user,db)}

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}

@app.post("/api/auth/register", status_code=201)
def register(data: Registration, db: Session = Depends(get_db)):
    minor = age(data.player_birth_date)<18
    user = User(username=data.username.lower(), password_hash=password_hash(data.password or secrets.token_urlsafe(32)),
                email=None if minor else data.email, phone=None if minor else data.phone,
                display_name=data.display_name, bio="" if minor else data.bio,player_birth_date=data.player_birth_date,
                account_status="pending_guardian" if minor else "active",guardian_managed=int(minor))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tên người dùng hoặc thông tin liên hệ đã được sử dụng.")
    if minor:
        start_guardian(db,user,data.guardian_email)
        db.commit()
        return {"status":"pending_guardian","message":"Yêu cầu xác nhận đã gửi qua email người đại diện. Chưa thể đăng nhập; người đại diện cần đọc chính sách và đặt mật khẩu quản lý."}
    record_consent(db,user)
    return session_response(user, db)

@app.post("/api/auth/login")
def login(data: Credentials, db: Session = Depends(get_db)):
    identifier = data.username.strip().lower()
    if "@" in identifier:
        user = db.scalar(select(User).where(User.email == identifier))
    elif identifier.startswith(("+", "0")) and re.fullmatch(r"[+0-9\s().-]+", identifier):
        # Legacy numeric usernames take precedence to preserve existing logins.
        user = db.scalar(select(User).where(User.username == identifier))
        if not user:
            try:
                user = db.scalar(select(User).where(User.phone == clean_phone(identifier)))
            except ValueError:
                user = None
    else:
        user = db.scalar(select(User).where(User.username == identifier))
    if not user or not hmac.compare_digest(user.password_hash, password_hash(data.password, user.password_hash.split(":")[0])):
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu chưa đúng.")
    if user.account_status != "active":
        raise HTTPException(403,"Tài khoản đang chờ người đại diện xác nhận hoặc đã dừng. Hãy kiểm tra email người đại diện/liên hệ hỗ trợ.")
    return session_response(user, db)

@app.post("/api/auth/logout", status_code=204)
def logout(user: User = Depends(current_user), authorization: str = Header(), db: Session = Depends(get_db)):
    token = db.get(Token, hashlib.sha256(authorization[7:].encode()).hexdigest())
    db.delete(token)
    db.commit()

@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return private_user(user,db)

@app.patch("/api/me")
def edit_profile(data: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    changes = data.model_dump(exclude_unset=True)
    email, phone = changes.get("email", user.email), changes.get("phone", user.phone)
    if not email and not phone:
        raise HTTPException(400, "Hãy giữ ít nhất một email hoặc số điện thoại.")
    for key, value in changes.items():
        setattr(user, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Thông tin liên hệ đã được sử dụng.")
    db.refresh(user)
    return private_user(user,db)

async def save_image(file, user, avatar=False):
    data = await file.read(8 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Ảnh tối đa 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                clean = ImageOps.exif_transpose(source).convert("RGB")
                if avatar:
                    clean = ImageOps.fit(clean, (512, 512), method=Image.Resampling.LANCZOS)
                else:
                    clean.thumbnail((1920, 1920))
                filename = f"{'avatar-' if avatar else ''}{user.id}-{secrets.token_hex(16)}.jpg"
                # Re-encode pixels only: no EXIF, GPS, original filename or metadata.
                clean.save(UPLOAD_DIR / filename, "JPEG", quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "File ảnh không hợp lệ. Hãy dùng JPEG, PNG hoặc WebP.")
    return f"/uploads/{filename}"

@app.post("/api/uploads", status_code=201)
async def upload(file: UploadFile = File(), rights_confirmed: bool = Form(default=False), user: User = Depends(participant), db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(400,"Cần xác nhận quyền sử dụng và quyền đăng ảnh trước khi tải lên.")
    image_url = await save_image(file,user)
    db.add(ContentAttestation(user_id=user.id,resource=image_url,legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    return {"image_url":image_url}

@app.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(), rights_confirmed: bool = Form(default=False), user: User = Depends(participant), db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(400,"Cần xác nhận quyền sử dụng ảnh đại diện trước khi tải lên.")
    user.avatar_url = await save_image(file, user, avatar=True)
    db.add(ContentAttestation(user_id=user.id,resource=user.avatar_url,legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    db.refresh(user)
    return private_user(user,db)

@app.delete("/api/me/avatar")
def remove_avatar(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.avatar_url = None
    db.commit()
    return private_user(user,db)

class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=1000)
    image_url: str = Field(max_length=255)
    answer: str = Field(min_length=2, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    content_rights_confirmed: bool = Field(default=False,strict=True)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: int = Field(default=150, ge=20, le=1000)

    @model_validator(mode="after")
    def valid_location(self):
        if not self.content_rights_confirmed:
            raise ValueError("Cần xác nhận quyền sử dụng ảnh và trách nhiệm nội dung.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Cần nhập cả vĩ độ và kinh độ.")
        if len(normalize(self.answer)) < 2 or not self.title.strip():
            raise ValueError("Tên thử thách và đáp án không hợp lệ.")
        if any(len(alias) > 200 or len(normalize(alias)) < 2 for alias in self.aliases):
            raise ValueError("Tên thay thế cần từ 2 đến 200 ký tự.")
        return self

def get_case(case_id, db):
    case = db.get(Case, case_id)
    if not case or db.get(User,case.creator_id).account_status != "active":
        raise HTTPException(404, "Không tìm thấy thử thách.")
    return case

def public_case(case, db, viewer=None):
    creator = db.get(User, case.creator_id)
    return {"id": case.id, "title": case.title, "description": case.description,
            "image_url": case.image_url, "creator": creator.username, "creator_id": creator.id,
            "creator_display_name": creator.display_name or creator.username, "creator_avatar_url": creator.avatar_url,
            "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case.id)),
            "liked_by_me": bool(viewer and db.scalar(select(Like.id).where(Like.user_id == viewer.id, Like.case_id == case.id))),
            "comments": db.scalar(select(func.count()).select_from(Comment).where(Comment.case_id == case.id)),
            "reward_xp": case.reward_xp, "has_coordinates": case.latitude is not None,
            "solves": db.scalar(select(func.count()).select_from(Solve).where(Solve.case_id == case.id)),
            "created_at": case.created_at}

@app.post("/api/cases", status_code=201)
def create_case(data: CaseCreate, user: User = Depends(participant), db: Session = Depends(get_db)):
    if user.guardian_managed and data.latitude is not None:
        raise HTTPException(403,"Tài khoản được người đại diện quản lý chưa sử dụng GPS trong bản thử nghiệm.")
    filename = data.image_url.removeprefix("/uploads/")
    if not re.fullmatch(rf"{user.id}-[a-f0-9]{{32}}\.jpg", filename) or not (UPLOAD_DIR / filename).is_file():
        raise HTTPException(400, "Vui lòng tải ảnh của bạn lên trước.")
    case = Case(**data.model_dump(exclude={"aliases","content_rights_confirmed"}), creator_id=user.id)
    db.add(case)
    db.flush()
    for answer in {normalize(alias) for alias in data.aliases} - {normalize(data.answer)}:
        db.add(AnswerAlias(case_id=case.id, answer=answer))
    db.add(ContentAttestation(user_id=user.id,resource=f"case:{case.id}",legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    db.refresh(case)
    return public_case(case, db, user)

@app.get("/api/cases")
def list_cases(offset: int = Query(default=0, ge=0), limit: int = Query(default=24, ge=1, le=100), db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    return [public_case(c, db, viewer) for c in db.scalars(select(Case).join(User,Case.creator_id==User.id).where(User.account_status=="active").order_by(Case.id.desc()).offset(offset).limit(limit))]

@app.get("/api/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    return public_case(get_case(case_id, db), db, viewer)

class Guess(BaseModel):
    answer: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

@app.post("/api/cases/{case_id}/guesses")
def guess(case_id: int, data: Guess, user: User = Depends(participant), db: Session = Depends(get_db)):
    if user.guardian_managed and data.latitude is not None:
        raise HTTPException(403,"Tài khoản được người đại diện quản lý chưa sử dụng GPS.")
    case = get_case(case_id, db)
    if case.creator_id == user.id:
        raise HTTPException(400, "Bạn là người tạo thử thách này.")
    if db.scalar(select(Solve).where(Solve.user_id == user.id, Solve.case_id == case_id)):
        return {"status": "already_solved", "reward_xp": 0}
    limit_attempt(db, user, case_id)
    _, correct = answer_matches(db, case, data.answer)
    if data.latitude is not None and data.longitude is not None and case.latitude is not None:
        lat1, lat2 = math.radians(case.latitude), math.radians(data.latitude)
        dlat, dlon = lat2 - lat1, math.radians(data.longitude - case.longitude)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        correct = correct or 6371000 * 2 * math.asin(math.sqrt(min(1, a))) <= case.radius_meters
    if not correct:
        db.commit()
        return {"status": "incorrect", "reward_xp": 0}
    status, xp = award_solve(db, case, user)
    db.commit()
    return {"status": status, "reward_xp": xp}

class CommentCreate(BaseModel):
    content: str = Field(default="", max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def valid_submission(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Cần đủ tọa độ vị trí.")
        if not self.content.strip() and self.latitude is None:
            raise ValueError("Hãy nhập bình luận hoặc lấy vị trí để dự đoán.")
        return self

@app.get("/api/cases/{case_id}/comments")
def comments(case_id: int, db: Session = Depends(get_db)):
    get_case(case_id, db)
    rows = db.scalars(select(Comment).where(Comment.case_id == case_id).order_by(Comment.id.desc()).limit(100))
    result = []
    for c in rows:
        author = db.get(User, c.user_id)
        if author.account_status != "active":
            result.append({"id":c.id,"username":"account-paused","display_name":"Tài khoản đã dừng","avatar_url":None,"content":"Bình luận không còn hiển thị.","is_hidden":True,"created_at":c.created_at})
            continue
        result.append({"id": c.id, "username": author.username,
             "display_name": author.display_name or author.username, "avatar_url": author.avatar_url,
             "content": "Đã ẩn nội dung dự đoán." if c.is_hidden else c.content,
             "is_hidden": bool(c.is_hidden), "created_at": c.created_at})
    return result

@app.post("/api/cases/{case_id}/comments", status_code=201)
def comment(case_id: int, data: CommentCreate, user: User = Depends(participant), db: Session = Depends(get_db)):
    if user.guardian_managed and data.latitude is not None:
        raise HTTPException(403,"Tài khoản được người đại diện quản lý chưa sử dụng GPS.")
    case = get_case(case_id, db)
    limit_attempt(db, user, case_id)
    content = data.content.strip()
    hidden, correct = answer_matches(db, case, content)
    if data.latitude is not None:
        if case.latitude is None:
            raise HTTPException(400, "Thử thách này chỉ nhận tên địa danh.")
        lat1, lat2 = math.radians(case.latitude), math.radians(data.latitude)
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(data.longitude - case.longitude) / 2) ** 2
        correct = correct or 6371000 * 2 * math.asin(math.sqrt(min(1, a))) <= case.radius_meters
        # Never expose coordinates or text sent alongside a GPS prediction.
        hidden = True
        content = "Dự đoán bằng vị trí (giữ riêng tư)."
    status, xp = award_solve(db, case, user) if correct else ("commented", 0)
    entry = Comment(case_id=case_id, user_id=user.id, content=content, is_hidden=int(hidden))
    db.add(entry)
    db.flush()
    if status != "correct":
        notify(db, case, user, "comment", entry.id)
    db.commit()
    return {"id": entry.id, "is_hidden": hidden, "status": status, "reward_xp": xp}

@app.put("/api/cases/{case_id}/like")
def like_case(case_id: int, user: User = Depends(participant), db: Session = Depends(get_db)):
    case = get_case(case_id, db)
    if not db.scalar(select(Like.id).where(Like.user_id == user.id, Like.case_id == case.id)):
        try:
            with db.begin_nested():
                db.add(Like(user_id=user.id, case_id=case.id))
                db.flush()
        except IntegrityError:
            pass
        notify(db, case, user, "like")
    db.commit()
    return {"liked_by_me": True, "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case.id))}

@app.delete("/api/cases/{case_id}/like")
def unlike_case(case_id: int, user: User = Depends(participant), db: Session = Depends(get_db)):
    get_case(case_id, db)
    db.execute(delete(Like).where(Like.user_id == user.id, Like.case_id == case_id))
    db.commit()
    return {"liked_by_me": False, "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case_id))}

@app.get("/api/notifications")
def notifications(before_id: int | None = Query(default=None, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Notification).where(Notification.recipient_id == user.id)
    if before_id:
        query = query.where(Notification.id < before_id)
    rows = list(db.scalars(query.order_by(Notification.id.desc()).limit(30)))
    items = []
    for row in rows:
        actor, case = db.get(User, row.actor_id), db.get(Case, row.case_id)
        actor_data = public_user(actor) if actor.account_status=="active" else {"id":actor.id,"username":"account-paused","display_name":"Tài khoản đã dừng","avatar_url":None}
        items.append({"id": row.id, "kind": row.kind, "actor": actor_data, "case_id": case.id,
                      "case_title": case.title if db.get(User,case.creator_id).account_status=="active" else "Bài không còn hiển thị", "is_read": bool(row.is_read), "created_at": row.created_at})
    return {"items": items, "unread_count": db.scalar(select(func.count()).select_from(Notification).where(Notification.recipient_id == user.id, Notification.is_read == 0)),
            "next_before_id": rows[-1].id if len(rows) == 30 else None}

class NotificationRead(BaseModel):
    through_id: int = Field(ge=1)

@app.post("/api/notifications/read")
def read_notifications(data: NotificationRead, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.recipient_id == user.id, Notification.id <= data.through_id).values(is_read=1))
    db.commit()
    return {"status": "ok"}

@app.post("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.recipient_id == user.id))
    if not entry:
        raise HTTPException(404, "Không tìm thấy thông báo.")
    entry.is_read = 1
    db.commit()
    return {"status": "ok"}

@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    return [public_user(u) for u in db.scalars(select(User).where(User.account_status=="active").order_by(User.total_xp.desc(), User.id).limit(20))]

app.include_router(build_router(current_user,password_hash))
