import json
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

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query, Form, Request, Cookie
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import ModerationAudit, User, Token, Case, Solve, Comment, Attempt, Like, Notification, AnswerAlias, ContentAttestation, ImageReview, PointAward, CaseShare, DailyReward, Bookmark, Follow, LoginSession
from .community import build_router as community_router, visible_cases, blocked_ids, is_blocked
from .password_reset import build_router as reset_router
from .login_sessions import build_router as session_router, record_session, touch_session
from .progression import progression, local_day
from .migrations import upgrade
from .image_safety import scan_image
from .email_verification import consume_registration_proof, build_router as email_router
from .auth_security import COOKIE_NAME, login_limits, throttle, check_password, consume_totp
from .moderation import build_router as moderation_router
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

@app.middleware('http')
async def staff_response_headers(request:Request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    if request.url.path.startswith(('/staff','/api/staff/','/api/moderation/','/static/staff')):
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['X-Content-Type-Options']='nosniff'
    if request.url.path.startswith('/api/cases/') and request.url.path.endswith('/comments'):
        response.headers['Cache-Control']='no-store'
    if request.url.path.startswith(('/api/email-verification/','/api/me/','/api/auth/password-reset/','/api/users/','/api/notifications')):
        response.headers['Cache-Control']='no-store'
    return response

def normalize(value):
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", value))

def public_user(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name or user.username,
            "bio": user.bio or "", "avatar_url": user.avatar_url,
            "xp": user.total_xp, **progression(user.total_xp)}

def private_user(user, db=None):
    return {**public_user(user), "email": user.email, "phone": user.phone,
            "contact_verified":bool(user.email and user.email_verified), "email_verified":bool(user.email and user.email_verified), "phone_verified":False, "guardian_managed":bool(user.guardian_managed),
            "needs_legal_consent":bool(db is not None and (not user.player_birth_date or not latest_consent(db,user))),
            "role":user.role, "player_birth_date":user.player_birth_date.isoformat() if user.player_birth_date else None, "legal_version":LEGAL_VERSION}

def current_user(request: Request, authorization: str = Header(default=""), staff_cookie: str | None = Cookie(default=None,alias=COOKIE_NAME), db: Session = Depends(get_db)):
    raw = authorization.removeprefix("Bearer ") if authorization else staff_cookie or ''
    if not authorization and staff_cookie and request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('X-JinHunt-Staff')!='1':
        raise HTTPException(403,'Yêu cầu quản trị không hợp lệ.')
    token = db.get(Token, hashlib.sha256(raw.encode()).hexdigest())
    if (authorization and not authorization.startswith("Bearer ")) or not token or token.expires_at < time.time():
        raise HTTPException(401, "Vui lòng đăng nhập lại.")
    user = db.get(User, token.user_id)
    if user.role in {"admin","moderator"} and not token.staff_verified:
        raise HTTPException(401,"Tài khoản quản trị cần đăng nhập qua /staff/login với mã OTP.")
    if user.account_status != "active" or user.suspended:
        raise HTTPException(403,"Tài khoản chưa được kích hoạt hoặc đã dừng. Hãy kiểm tra xác nhận người đại diện hoặc liên hệ hỗ trợ.")
    touch_session(db,request,token)
    return user

def participant(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.player_birth_date or not latest_consent(db,user):
        raise HTTPException(403,"Cần xác nhận độ tuổi, Điều khoản sử dụng và Chính sách quyền riêng tư trong tài khoản trước khi tham gia.")
    return user

def optional_user(request: Request, authorization: str = Header(default=""), staff_cookie: str | None = Cookie(default=None,alias=COOKIE_NAME), db: Session = Depends(get_db)):
    if authorization: return current_user(request,authorization,None,db)
    if staff_cookie:
        try: return current_user(request,'',staff_cookie,db)
        except HTTPException as error:
            if error.status_code not in {401,403}: raise
    return None

@app.get('/uploads/{filename}',include_in_schema=False)
def uploaded_image(filename:str,db:Session=Depends(get_db),viewer:User|None=Depends(optional_user)):
    match=re.fullmatch(r"(?:avatar-)?([0-9]+)-[a-f0-9]{32}\.jpg",filename)
    owner=db.get(User,int(match.group(1))) if match else None
    url='/uploads/'+filename
    review=db.get(ImageReview,url)
    staff=bool(viewer and viewer.role in {'moderator','admin'})
    private=bool(viewer and (viewer.id==int(match.group(1)) if match else False)) or staff
    published=db.scalar(select(Case.id).where(Case.image_url==url,Case.moderation_status=='published'))
    visible=owner and owner.account_status=='active' and not owner.suspended and (not review or review.status=='approved') and (owner.avatar_url==url or published)
    if not owner or not (upload_dir_path:=UPLOAD_DIR/filename).is_file() or (not visible and not private) or (review and review.status=='removed' and not staff):
        raise HTTPException(404,'Không tìm thấy ảnh.')
    return FileResponse(upload_dir_path,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

async def review_upload(image_url,user,db):
    scan=await run_in_threadpool(scan_image,UPLOAD_DIR/image_url.split('/')[-1])
    auto_clean = (os.getenv('AUTO_APPROVE_SCANNED','1')=='1'
                  and scan.get('state')=='scanned' and scan.get('sensitive') is False)
    development_bypass = os.getenv('MODERATION_REQUIRE_REVIEW','1')=='0'
    status='approved' if auto_clean or (development_bypass and not scan.get('sensitive') and scan.get('state')!='error') else 'pending'
    scan['decision']='auto_approved' if auto_clean else 'development_bypass' if status=='approved' else 'human_review'
    db.add(ImageReview(image_url=image_url,user_id=user.id,status=status,scan=json.dumps(scan,ensure_ascii=False),created_at=time.time()))
    return status,scan

def notify(db, case, actor, kind, source_id=None):
    if case.creator_id == actor.id or is_blocked(db,actor,case.creator_id):
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

def daily_reward(db,user_id,kind,points):
    day=local_day()
    try:
        with db.begin_nested():
            db.add(DailyReward(user_id=user_id,day=day,kind=kind,points=points))
            db.flush()
            db.execute(update(User).where(User.id==user_id).values(total_xp=User.total_xp+points))
        return points
    except IntegrityError:
        return 0


@app.get("/api/me/progress")
def daily_progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    day=local_day()
    kinds=set(db.scalars(select(DailyReward.kind).where(DailyReward.user_id==user.id,DailyReward.day==day)))
    return {"day":day.isoformat(),"timezone":"Asia/Ho_Chi_Minh","checkin_done":"checkin" in kinds,"checkin_points":5,"solve_done":"solve" in kinds,"solve_points":10}


@app.post("/api/me/checkin")
def checkin(user: User = Depends(participant), db: Session = Depends(get_db)):
    points=daily_reward(db,user.id,"checkin",5)
    db.commit()
    db.refresh(user)
    return {"reward_xp":points,"user":private_user(user,db)}


def award_points(db, user_id, case_id, kind, points):
    try:
        with db.begin_nested():
            db.add(PointAward(user_id=user_id,case_id=case_id,kind=kind,points=points))
            db.flush()
            db.execute(update(User).where(User.id==user_id).values(total_xp=User.total_xp+points))
        return points
    except IntegrityError:
        return 0


def reward_share(db, case, actor, share_token):
    if not share_token or actor.id==case.creator_id:
        return
    share=db.get(CaseShare,share_token)
    if share and share.case_id==case.id and share.user_id==case.creator_id:
        award_points(db,case.creator_id,case.id,"share",10)


def award_solve(db, case, user):
    if case.creator_id == user.id:
        return "author", 0
    # Serialize awards per case in both PostgreSQL and SQLite before counting.
    db.execute(update(Case).where(Case.id==case.id).values(reward_xp=Case.reward_xp))
    if db.scalar(select(Solve).where(Solve.user_id == user.id, Solve.case_id == case.id)):
        return "already_solved", 0
    rank=db.scalar(select(func.count()).select_from(Solve).where(Solve.case_id==case.id))
    points=(50,25,10)[rank] if rank<3 else 5
    try:
        with db.begin_nested():
            db.add(Solve(user_id=user.id, case_id=case.id))
            db.flush()
            award_points(db,user.id,case.id,"solve",points)
    except IntegrityError:
        return "already_solved", 0
    daily_reward(db,user.id,"solve",10)
    notify(db, case, user, "solve")
    return "correct", points

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
    email_verification_token: str | None = Field(default=None,max_length=128)
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

def session_response(user, db, request=None):
    raw = secrets.token_urlsafe(32)
    session=Token(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires_at=time.time() + 86400 * 7)
    db.add(session);record_session(db,request,session)
    db.commit()
    return {"token": raw, "user": private_user(user,db)}

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get('/verify-email',include_in_schema=False)
def email_link_page():
    return FileResponse(STATIC_DIR/'verify-email.html',headers=staff_page_headers())

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}

@app.post("/api/auth/register", status_code=201)
def register(data: Registration, request:Request, db: Session = Depends(get_db)):
    minor = age(data.player_birth_date)<18
    if not minor and data.email:
        if db.scalar(select(User.id).where((User.email==data.email)|(User.username==data.username.lower()))):
            raise HTTPException(409,"Tên người dùng hoặc email đã được sử dụng.")
        consume_registration_proof(db,data.email,data.email_verification_token)
    user = User(username=data.username.lower(), password_hash=password_hash(data.password or secrets.token_urlsafe(32)),
                email=None if minor else data.email, email_verified=int(not minor and bool(data.email)), phone=None if minor else data.phone,
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
    return session_response(user, db, request)

@app.post("/api/auth/login")
def login(data: Credentials, request: Request, db: Session = Depends(get_db)):
    identifier = data.username.strip().lower()
    login_limits(db,request,identifier)
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
    if user: throttle(db,"account",str(user.id),8)
    if not check_password(user,data.password,password_hash):
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu chưa đúng.")
    if user.account_status != "active" or user.suspended:
        raise HTTPException(403,"Tài khoản đang chờ người đại diện xác nhận hoặc đã dừng. Hãy kiểm tra email người đại diện/liên hệ hỗ trợ.")
    if user.role in {"admin","moderator"}:
        raise HTTPException(403,"Tài khoản quản trị dùng trang /staff/login và mã xác thực OTP.")
    return session_response(user, db, request)

@app.post("/api/auth/logout", status_code=204)
def logout(user: User = Depends(current_user), authorization: str = Header(), db: Session = Depends(get_db)):
    token = db.get(Token, hashlib.sha256(authorization[7:].encode()).hexdigest())
    db.execute(update(LoginSession).where(LoginSession.token_hash==token.token_hash).values(ended_at=time.time()))
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
    if email!=user.email:
        if user.guardian_managed: raise HTTPException(403,"Liên hệ hỗ trợ để đổi email người đại diện.")
        if email:
            if db.scalar(select(User.id).where(User.email==email,User.id!=user.id)):
                raise HTTPException(409,"Thông tin liên hệ đã được sử dụng.")
            raise HTTPException(400,"Hãy gửi mã và xác minh email mới trước khi lưu hồ sơ.")
        user.email_verified=0
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
    status,scan=await review_upload(image_url,user,db)
    db.add(ContentAttestation(user_id=user.id,resource=image_url,legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    return {"image_url":image_url,"moderation_status":status,"scan":scan}

@app.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(), rights_confirmed: bool = Form(default=False), user: User = Depends(participant), db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(400,"Cần xác nhận quyền sử dụng ảnh đại diện trước khi tải lên.")
    image_url = await save_image(file, user, avatar=True)
    status,scan=await review_upload(image_url,user,db)
    if status=="approved": user.avatar_url=image_url
    db.add(ContentAttestation(user_id=user.id,resource=image_url,legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    db.refresh(user)
    return {**private_user(user,db),"moderation_status":status,"scan":scan}

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

def get_case(case_id, db, viewer=None):
    case = db.get(Case, case_id)
    if not case or case.moderation_status != "published" or db.get(User,case.creator_id).account_status != "active" or db.get(User,case.creator_id).suspended:
        raise HTTPException(404, "Không tìm thấy thử thách.")
    if is_blocked(db,viewer,case.creator_id):raise HTTPException(404,'Không tìm thấy thử thách.')
    return case

def public_case(case, db, viewer=None):
    creator = db.get(User, case.creator_id)
    return {"id": case.id, "title": case.title, "description": case.description,
            "moderation_status":case.moderation_status, "image_url": case.image_url, "creator": creator.username, "creator_id": creator.id,
            "creator_display_name": creator.display_name or creator.username, "creator_avatar_url": creator.avatar_url, "creator_level":progression(creator.total_xp)["level"],
            "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case.id)),
            "bookmarked_by_me":bool(viewer and db.scalar(select(Bookmark.id).where(Bookmark.user_id==viewer.id,Bookmark.case_id==case.id))),
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
    review=db.get(ImageReview,data.image_url)
    case.moderation_status="published" if review and review.status=="approved" else "pending"
    if review and review.status=="removed": raise HTTPException(400,"Ảnh đã bị gỡ; hãy tải ảnh khác.")
    db.add(case)
    db.flush()
    for answer in {normalize(alias) for alias in data.aliases} - {normalize(data.answer)}:
        db.add(AnswerAlias(case_id=case.id, answer=answer))
    db.add(ContentAttestation(user_id=user.id,resource=f"case:{case.id}",legal_version=LEGAL_VERSION,accepted_at=time.time()))
    db.commit()
    db.refresh(case)
    return public_case(case, db, user)

@app.get("/api/cases")
def list_cases(offset: int = Query(default=0, ge=0), limit: int = Query(default=24, ge=1, le=100), q: str = Query(default="", max_length=100), following:bool=False, db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    query=visible_cases(db,viewer)
    if following:
        if not viewer:raise HTTPException(401,'Đăng nhập để xem bài đang theo dõi.')
        query=query.where(Case.creator_id.in_(select(Follow.target_id).where(Follow.user_id==viewer.id)))
    if q.strip():
        escaped=q.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        query=query.where(Case.title.ilike('%'+escaped+'%',escape='\\') | Case.description.ilike('%'+escaped+'%',escape='\\'))
    return [public_case(c,db,viewer) for c in db.scalars(query.order_by(Case.id.desc()).offset(offset).limit(limit))]

@app.get("/api/me/cases")
def my_cases(offset: int = Query(default=0, ge=0), limit: int = Query(default=12, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [public_case(c, db, user) for c in db.scalars(select(Case).where(Case.creator_id==user.id).order_by(Case.id.desc()).offset(offset).limit(limit))]

@app.get("/api/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    return public_case(get_case(case_id, db, viewer), db, viewer)

class Guess(BaseModel):
    share_token: str | None = Field(default=None, max_length=64)
    answer: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

@app.post("/api/cases/{case_id}/guesses")
def guess(case_id: int, data: Guess, user: User = Depends(participant), db: Session = Depends(get_db)):
    if user.guardian_managed and data.latitude is not None:
        raise HTTPException(403,"Tài khoản được người đại diện quản lý chưa sử dụng GPS.")
    case = get_case(case_id, db, user)
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
    reward_share(db,case,user,data.share_token)
    db.commit()
    return {"status": status, "reward_xp": xp}

class CommentCreate(BaseModel):
    share_token: str | None = Field(default=None, max_length=64)
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
def comments(case_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    case = get_case(case_id, db, viewer)
    can_read_answers = bool(viewer and (viewer.id == case.creator_id or db.scalar(select(Solve.id).where(Solve.case_id == case_id, Solve.user_id == viewer.id))))
    rows = db.scalars(select(Comment).where(Comment.case_id == case_id).order_by(Comment.id.desc()).limit(100))
    result = []
    excluded=blocked_ids(db,viewer)
    for c in rows:
        if c.user_id in excluded:continue
        author = db.get(User, c.user_id)
        if c.is_removed or author.account_status != "active" or author.suspended:
            result.append({"id":c.id,"username":"account-paused","display_name":"Tài khoản đã dừng","avatar_url":None,"content":"Bình luận không còn hiển thị.","is_hidden":True,"created_at":c.created_at})
            continue
        result.append({"id": c.id, "user_id":author.id, "username": author.username,
             "display_name": author.display_name or author.username, "avatar_url": author.avatar_url, "level":progression(author.total_xp)["level"],
             "content": "Đã ẩn nội dung dự đoán." if c.is_hidden and not can_read_answers else c.content,
             "is_hidden": bool(c.is_hidden and not can_read_answers), "created_at": c.created_at})
    return result

@app.post("/api/cases/{case_id}/comments", status_code=201)
def comment(case_id: int, data: CommentCreate, user: User = Depends(participant), db: Session = Depends(get_db)):
    if user.guardian_managed and data.latitude is not None:
        raise HTTPException(403,"Tài khoản được người đại diện quản lý chưa sử dụng GPS.")
    case = get_case(case_id, db, user)
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
    interaction_xp=award_points(db,user.id,case.id,"comment",1) if user.id!=case.creator_id else 0
    reward_share(db,case,user,data.share_token)
    if status != "correct":
        notify(db, case, user, "comment", entry.id)
    db.commit()
    return {"id": entry.id, "is_hidden": hidden, "status": status, "reward_xp": xp, "interaction_xp":interaction_xp}

@app.put("/api/cases/{case_id}/like")
def like_case(case_id: int, share_token: str | None = Query(default=None,max_length=64), user: User = Depends(participant), db: Session = Depends(get_db)):
    case = get_case(case_id, db, user)
    if not db.scalar(select(Like.id).where(Like.user_id == user.id, Like.case_id == case.id)):
        try:
            with db.begin_nested():
                db.add(Like(user_id=user.id, case_id=case.id))
                db.flush()
        except IntegrityError:
            pass
        notify(db, case, user, "like")
    if user.id!=case.creator_id:
        award_points(db,user.id,case.id,"like",1)
        reward_share(db,case,user,share_token)
    db.commit()
    return {"liked_by_me": True, "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case.id))}

@app.post("/api/cases/{case_id}/share")
def share_case(case_id: int, user: User = Depends(participant), db: Session = Depends(get_db)):
    case=get_case(case_id,db,user)
    if user.id!=case.creator_id:
        return {"share_token":None}
    db.execute(update(Case).where(Case.id==case.id).values(reward_xp=Case.reward_xp))
    share=db.scalar(select(CaseShare).where(CaseShare.case_id==case.id))
    if not share:
        share=CaseShare(token=secrets.token_urlsafe(32),case_id=case.id,user_id=user.id)
        db.add(share)
    db.commit()
    return {"share_token":share.token}

@app.delete("/api/cases/{case_id}/like")
def unlike_case(case_id: int, user: User = Depends(participant), db: Session = Depends(get_db)):
    get_case(case_id, db, user)
    db.execute(delete(Like).where(Like.user_id == user.id, Like.case_id == case_id))
    db.commit()
    return {"liked_by_me": False, "likes": db.scalar(select(func.count()).select_from(Like).where(Like.case_id == case_id))}

@app.get("/api/notifications")
def notifications(before_id: int | None = Query(default=None, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Page by whole groups, never by individual events inside a group.
    excluded=blocked_ids(db,user)
    groups = select(func.max(Notification.id).label("latest_id")).where(Notification.recipient_id == user.id,Notification.actor_id.not_in(excluded)).group_by(Notification.case_id, Notification.kind).subquery()
    query = select(groups.c.latest_id)
    if before_id:
        query = query.where(groups.c.latest_id < before_id)
    ids = list(db.scalars(query.order_by(groups.c.latest_id.desc()).limit(31)))
    items = []
    for latest_id in ids[:30]:
        row = db.get(Notification, latest_id)
        scope = (Notification.recipient_id == user.id, Notification.case_id == row.case_id, Notification.kind == row.kind, Notification.id <= latest_id, Notification.actor_id.not_in(excluded))
        actor_ids = list(db.scalars(select(Notification.actor_id).where(*scope).group_by(Notification.actor_id).order_by(func.max(Notification.id).desc()).limit(2)))
        actors = []
        for actor_id in actor_ids:
            actor = db.get(User, actor_id)
            actors.append(public_user(actor) if actor.account_status=="active" and not actor.suspended else {"id":actor.id,"username":"account-paused","display_name":"Tài khoản đã dừng","avatar_url":None})
        actor_count = db.scalar(select(func.count(func.distinct(Notification.actor_id))).where(*scope))
        unread = db.scalar(select(func.count()).select_from(Notification).where(*scope, Notification.is_read == 0))
        case = db.get(Case, row.case_id) if row.case_id is not None else None
        items.append({"id":row.id,"kind":row.kind,"actor":actors[0],"actors":actors,"actor_count":actor_count,"case_id":case.id if case else None,"target_user_id":actors[0]["id"] if row.kind=="follow" else None,
                      "case_title":(case.title if db.get(User,case.creator_id).account_status=="active" else "Bài không còn hiển thị") if case else None,"is_read":not bool(unread),"created_at":row.created_at})
    unread_groups = select(Notification.case_id, Notification.kind).where(Notification.recipient_id==user.id, Notification.is_read==0,Notification.actor_id.not_in(excluded)).group_by(Notification.case_id,Notification.kind).subquery()
    return {"items":items,"unread_count":db.scalar(select(func.count()).select_from(unread_groups)),"next_before_id":ids[29] if len(ids)>30 else None}

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
    # Only acknowledge events included in the clicked group's snapshot.
    db.execute(update(Notification).where(Notification.recipient_id==user.id, Notification.case_id==entry.case_id, Notification.kind==entry.kind, Notification.id<=entry.id).values(is_read=1))
    db.commit()
    return {"status": "ok"}

@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db),viewer:User|None=Depends(optional_user)):
    return [public_user(u) for u in db.scalars(select(User).where(User.account_status=="active",User.suspended==0,User.is_test==0,User.id.not_in(blocked_ids(db,viewer))).order_by(User.total_xp.desc(), User.id).limit(20))]

app.include_router(community_router(current_user,participant,optional_user,public_user,public_case,get_case))
app.include_router(reset_router(clean_email,password_hash,current_user))
app.include_router(session_router(current_user))
app.include_router(build_router(current_user,password_hash))

app.include_router(moderation_router(current_user,get_case,UPLOAD_DIR))

@app.get('/staff/login',include_in_schema=False)
def staff_login_page():
    return FileResponse(STATIC_DIR/'staff-login.html',headers=staff_page_headers())

@app.get('/staff',include_in_schema=False)
def staff_page():
    return FileResponse(STATIC_DIR/'staff.html',headers=staff_page_headers())

def staff_page_headers():
    return {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"}

class StaffCredentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username: str = Field(min_length=1,max_length=254)
    password: str = Field(min_length=1,max_length=128)
    otp: str = Field(pattern=r'^[0-9]{6}$')

@app.post('/api/staff/login')
def staff_login(data:StaffCredentials,request:Request,db:Session=Depends(get_db)):
    if request.headers.get('X-JinHunt-Staff')!='1':
        raise HTTPException(403,'Yêu cầu đăng nhập quản trị không hợp lệ.')
    secure=os.getenv('STAFF_COOKIE_SECURE','1')!='0'
    if secure and request.url.scheme!='https':
        raise HTTPException(426,'Đăng nhập quản trị cần HTTPS.')
    identifier=data.username.strip().lower()
    login_limits(db,request,identifier)
    user=db.scalar(select(User).where(User.username==identifier))
    if user: throttle(db,'account',str(user.id),8)
    valid_password=check_password(user,data.password,password_hash)
    if not valid_password or user.role not in {'admin','moderator'} or user.guardian_managed or user.suspended or user.account_status!='active':
        raise HTTPException(401,'Thông tin đăng nhập hoặc mã xác thực chưa đúng.')
    if not consume_totp(db,user,data.otp):
        raise HTTPException(401,'Thông tin đăng nhập hoặc mã xác thực chưa đúng.')
    raw=secrets.token_urlsafe(32)
    session=Token(token_hash=hashlib.sha256(raw.encode()).hexdigest(),user_id=user.id,expires_at=time.time()+8*3600,staff_verified=1)
    db.add(session);record_session(db,request,session)
    db.add(ModerationAudit(actor_id=user.id,action='staff_login',target=f'user:{user.id}',reason='Password and TOTP verified',created_at=time.time()))
    db.commit()
    response=JSONResponse({'status':'ok'},headers={'Cache-Control':'no-store'})
    response.set_cookie(COOKIE_NAME,raw,max_age=8*3600,httponly=True,secure=secure,samesite='strict',path='/')
    return response

@app.get('/api/staff/session')
def staff_session(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if user.role not in {'admin','moderator'}: raise HTTPException(403,'Cần quyền kiểm duyệt viên.')
    return private_user(user,db)

@app.post('/api/staff/logout')
def staff_logout(user:User=Depends(current_user),staff_cookie:str|None=Cookie(default=None,alias=COOKIE_NAME),db:Session=Depends(get_db)):
    if staff_cookie: db.execute(delete(Token).where(Token.token_hash==hashlib.sha256(staff_cookie.encode()).hexdigest()))
    db.commit()
    response=JSONResponse({'status':'ok'},headers={'Cache-Control':'no-store'})
    response.delete_cookie(COOKIE_NAME,path='/',secure=os.getenv('STAFF_COOKIE_SECURE','1')!='0',httponly=True,samesite='strict')
    return response

app.include_router(email_router(current_user,clean_email,private_user))
