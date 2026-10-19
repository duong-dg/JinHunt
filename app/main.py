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

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import User, Token, Case, Solve, Comment, Attempt
from .migrations import upgrade

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app):
    upgrade(engine)
    yield

app = FastAPI(title="JinHunt API", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def normalize(value):
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", value))

def public_user(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name or user.username,
            "bio": user.bio or "", "avatar_url": user.avatar_url,
            "xp": user.total_xp, "level": user.total_xp // 200 + 1}

def private_user(user):
    return {**public_user(user), "email": user.email, "phone": user.phone,
            "contact_verified": False}

def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    raw = authorization.removeprefix("Bearer ")
    token = db.get(Token, hashlib.sha256(raw.encode()).hexdigest())
    if not authorization.startswith("Bearer ") or not token or token.expires_at < time.time():
        raise HTTPException(401, "Vui lòng đăng nhập lại.")
    return db.get(User, token.user_id)

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

class Registration(ProfileUpdate):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,30}$")
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_contact(self):
        if not self.email and not self.phone:
            raise ValueError("Cần cung cấp email hoặc số điện thoại.")
        return self

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"

def session_response(user, db):
    raw = secrets.token_urlsafe(32)
    db.add(Token(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires_at=time.time() + 86400 * 7))
    db.commit()
    return {"token": raw, "user": private_user(user)}

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}

@app.post("/api/auth/register", status_code=201)
def register(data: Registration, db: Session = Depends(get_db)):
    user = User(username=data.username.lower(), password_hash=password_hash(data.password),
                email=data.email, phone=data.phone, display_name=data.display_name, bio=data.bio)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tên người dùng hoặc thông tin liên hệ đã được sử dụng.")
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
    return session_response(user, db)

@app.post("/api/auth/logout", status_code=204)
def logout(user: User = Depends(current_user), authorization: str = Header(), db: Session = Depends(get_db)):
    token = db.get(Token, hashlib.sha256(authorization[7:].encode()).hexdigest())
    db.delete(token)
    db.commit()

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return private_user(user)

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
    return private_user(user)

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
async def upload(file: UploadFile = File(), user: User = Depends(current_user)):
    return {"image_url": await save_image(file, user)}

@app.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.avatar_url = await save_image(file, user, avatar=True)
    db.commit()
    db.refresh(user)
    return private_user(user)

@app.delete("/api/me/avatar")
def remove_avatar(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.avatar_url = None
    db.commit()
    return private_user(user)

class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=1000)
    image_url: str = Field(max_length=255)
    answer: str = Field(min_length=2, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: int = Field(default=150, ge=20, le=1000)

    @model_validator(mode="after")
    def valid_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Cần nhập cả vĩ độ và kinh độ.")
        if len(normalize(self.answer)) < 2 or not self.title.strip():
            raise ValueError("Tên thử thách và đáp án không hợp lệ.")
        return self

def get_case(case_id, db):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Không tìm thấy thử thách.")
    return case

def public_case(case, db):
    creator = db.get(User, case.creator_id)
    return {"id": case.id, "title": case.title, "description": case.description,
            "image_url": case.image_url, "creator": creator.username, "creator_id": creator.id,
            "creator_display_name": creator.display_name or creator.username, "creator_avatar_url": creator.avatar_url,
            "reward_xp": case.reward_xp, "has_coordinates": case.latitude is not None,
            "solves": db.scalar(select(func.count()).select_from(Solve).where(Solve.case_id == case.id)),
            "created_at": case.created_at}

@app.post("/api/cases", status_code=201)
def create_case(data: CaseCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    filename = data.image_url.removeprefix("/uploads/")
    if not re.fullmatch(rf"{user.id}-[a-f0-9]{{32}}\.jpg", filename) or not (UPLOAD_DIR / filename).is_file():
        raise HTTPException(400, "Vui lòng tải ảnh của bạn lên trước.")
    case = Case(**data.model_dump(), creator_id=user.id)
    db.add(case)
    db.commit()
    db.refresh(case)
    return public_case(case, db)

@app.get("/api/cases")
def list_cases(offset: int = Query(default=0, ge=0), limit: int = Query(default=24, ge=1, le=100), db: Session = Depends(get_db)):
    return [public_case(c, db) for c in db.scalars(select(Case).order_by(Case.id.desc()).offset(offset).limit(limit))]

@app.get("/api/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db)):
    return public_case(get_case(case_id, db), db)

class Guess(BaseModel):
    answer: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

@app.post("/api/cases/{case_id}/guesses")
def guess(case_id: int, data: Guess, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(case_id, db)
    if case.creator_id == user.id:
        raise HTTPException(400, "Bạn là người tạo thử thách này.")
    if db.scalar(select(Solve).where(Solve.user_id == user.id, Solve.case_id == case_id)):
        return {"status": "already_solved", "reward_xp": 0}
    recent = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == user.id, Attempt.created_at > time.time() - 60))
    if recent >= 10:
        raise HTTPException(429, "Bạn đã đoán 10 lần. Hãy chờ một phút.")
    db.add(Attempt(user_id=user.id, case_id=case_id, created_at=time.time()))
    correct = normalize(data.answer) == normalize(case.answer)
    if data.latitude is not None and data.longitude is not None and case.latitude is not None:
        lat1, lat2 = math.radians(case.latitude), math.radians(data.latitude)
        dlat, dlon = lat2 - lat1, math.radians(data.longitude - case.longitude)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        correct = correct or 6371000 * 2 * math.asin(math.sqrt(min(1, a))) <= case.radius_meters
    if not correct:
        db.commit()
        return {"status": "incorrect", "reward_xp": 0}
    db.add(Solve(user_id=user.id, case_id=case_id))
    try:
        db.flush()
        db.execute(update(User).where(User.id == user.id).values(total_xp=User.total_xp + case.reward_xp))
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_solved", "reward_xp": 0}
    return {"status": "correct", "reward_xp": case.reward_xp}

class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)

@app.get("/api/cases/{case_id}/comments")
def comments(case_id: int, db: Session = Depends(get_db)):
    get_case(case_id, db)
    rows = db.scalars(select(Comment).where(Comment.case_id == case_id).order_by(Comment.id.desc()).limit(100))
    result = []
    for c in rows:
        author = db.get(User, c.user_id)
        result.append({"id": c.id, "username": author.username,
             "display_name": author.display_name or author.username, "avatar_url": author.avatar_url,
             "content": "Đã ẩn nội dung có đáp án." if c.is_hidden else c.content,
             "is_hidden": bool(c.is_hidden), "created_at": c.created_at})
    return result

@app.post("/api/cases/{case_id}/comments", status_code=201)
def comment(case_id: int, data: CommentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(case_id, db)
    content = data.content.strip()
    if not content:
        raise HTTPException(400, "Bình luận không được để trống.")
    hidden = f" {normalize(case.answer)} " in f" {normalize(content)} "
    db.add(Comment(case_id=case_id, user_id=user.id, content=content, is_hidden=int(hidden)))
    db.commit()
    return {"is_hidden": hidden}

@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    return [public_user(u) for u in db.scalars(select(User).order_by(User.total_xp.desc(), User.id).limit(20))]
