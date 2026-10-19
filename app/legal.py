import hashlib
import json
import os
import re
import secrets
import smtplib
import ssl
import time
from datetime import date, datetime
from email.message import EmailMessage
from html import escape
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator
from sqlalchemy import select, delete, func, update
from sqlalchemy.exc import IntegrityError
from .database import get_db
from .models import User, Token, LegalConsent, GuardianInvite, LegalRequest
from .legal_docs import DOCUMENTS, VERSION

def today():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()

def age(born):
    now = today()
    return now.year - born.year - ((now.month, now.day) < (born.month, born.day))

def email_address(value):
    value = (value or "").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[a-zA-Z]{2,63}", value) or len(value) > 254:
        raise ValueError("Email liên hệ không hợp lệ.")
    return value

class ConsentInput(BaseModel):
    terms_accepted: StrictBool
    privacy_accepted: StrictBool
    legal_version: Literal[VERSION]
    player_birth_date: date
    guardian_email: str | None = Field(default=None, max_length=254)

    @field_validator("terms_accepted", "privacy_accepted")
    @classmethod
    def must_agree(cls, value):
        if not value:
            raise ValueError("Cần chủ động đồng ý điều khoản và xử lý dữ liệu cần thiết.")
        return value

    @field_validator("player_birth_date")
    @classmethod
    def valid_birth(cls, value):
        if value > today() or value < date(1900, 1, 1):
            raise ValueError("Ngày sinh không hợp lệ.")
        return value

    @field_validator("guardian_email")
    @classmethod
    def valid_guardian_email(cls, value):
        return email_address(value) if value else None

    @model_validator(mode="after")
    def minor_guardian(self):
        if age(self.player_birth_date) < 18 and not self.guardian_email:
            raise ValueError("Người chơi dưới 18 tuổi cần email người đại diện để tạo tài khoản được quản lý.")
        return self

def operator_info():
    return {key: os.getenv(env, "").strip() for key, env in {
        "name":"LEGAL_OPERATOR_NAME", "address":"LEGAL_OPERATOR_ADDRESS", "email":"LEGAL_CONTACT_EMAIL",
        "hosting":"LEGAL_HOSTING_LOCATION", "providers":"LEGAL_SERVICE_PROVIDERS"}.items()}

def notice_snapshot():
    return json.dumps({"version":VERSION,"operator":operator_info(),"documents":{
        key:hashlib.sha256(value[2].encode()).hexdigest() for key,value in DOCUMENTS.items()},
        "document_texts":{key:value[2] for key,value in DOCUMENTS.items()}},ensure_ascii=False)

def latest_consent(db, user):
    return db.scalar(select(LegalConsent).where(LegalConsent.user_id == user.id, LegalConsent.version == VERSION,
                     LegalConsent.withdrawn_at.is_(None)).order_by(LegalConsent.id.desc()))

def record_consent(db, user, actor_type="adult", **values):
    db.add(LegalConsent(user_id=user.id,version=VERSION,notice_snapshot=notice_snapshot(),
                        actor_type=actor_type,accepted_at=time.time(),**values))

def send_guardian_email(recipient, link):
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    if not host or not sender:
        raise HTTPException(503,"Chưa cấu hình email xác nhận người đại diện. Tài khoản dưới 18 tuổi chưa được tạo/kích hoạt; vui lòng thử lại sau.")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, "JinHunt — Yêu cầu người đại diện quản lý tài khoản"
    message.set_content(f"Có yêu cầu tạo tài khoản JinHunt do bạn quản lý cho người chơi dưới 18 tuổi. Nếu bạn có quyền đại diện, hãy đọc chính sách và đặt mật khẩu tại:\n{link}\n\nLiên kết hết hạn sau 48 giờ, chỉ dùng một lần. Không chia sẻ liên kết hoặc mật khẩu với người khác. Nếu không biết yêu cầu này, bỏ qua email. Email xác nhận không phải xác minh danh tính/quan hệ đại diện.")
    try:
        mode = os.getenv("SMTP_SECURITY","starttls")
        if mode not in {"starttls","ssl"}:
            raise ValueError("SMTP must use TLS")
        port=int(os.getenv("SMTP_PORT","465" if mode == "ssl" else "587"))
        connection = smtplib.SMTP_SSL(host,port,timeout=15,context=ssl.create_default_context()) if mode == "ssl" else smtplib.SMTP(host,port,timeout=15)
        with connection as smtp:
            if mode == "starttls": smtp.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USER"): smtp.login(os.getenv("SMTP_USER"),os.getenv("SMTP_PASSWORD",""))
            smtp.send_message(message)
    except Exception:
        raise HTTPException(503,"Chưa gửi được email xác nhận. Tài khoản chưa được kích hoạt; vui lòng thử lại sau.")

def start_guardian(db, user, email):
    recent = db.scalar(select(func.count()).select_from(GuardianInvite).where(GuardianInvite.guardian_email==email,GuardianInvite.created_at>time.time()-3600))
    if recent>=3: raise HTTPException(429,"Email người đại diện đã nhận 3 yêu cầu trong một giờ. Hãy chờ trước khi thử lại.")
    base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost","127.0.0.1"}):
        raise HTTPException(503,"Cần cấu hình địa chỉ HTTPS để gửi xác nhận người đại diện.")
    raw = secrets.token_urlsafe(32)
    db.execute(update(GuardianInvite).where(GuardianInvite.user_id==user.id,GuardianInvite.used_at.is_(None)).values(expires_at=0))
    db.add(GuardianInvite(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id,
                         guardian_email=email, expires_at=time.time()+48*3600,created_at=time.time()))
    db.flush()
    # Fragment keeps bearer token out of server access logs and Referer headers.
    send_guardian_email(email,base+"/guardian-consent#token="+raw)
    user.account_status, user.guardian_managed = "pending_guardian", 1
    db.execute(delete(Token).where(Token.user_id == user.id))

def legal_page(title, intro, body):
    info = operator_info()
    draft = not all(info.values())
    metadata = "".join(f"<dt>{label}</dt><dd>{escape(info[key]) if info[key] else 'Chưa cung cấp — cần hoàn thiện trước khi phát hành'}</dd>" for key,label in [("name","Bên vận hành"),("address","Địa chỉ liên hệ"),("email","Email tiếp nhận"),("hosting","Nơi lưu trữ"),("providers","Nhà cung cấp xử lý")])
    banner = '<p class="draft-notice">BẢN DỰ THẢO ĐỂ XEM XÉT — Thông tin vận hành chưa đầy đủ. Chưa thể coi tài liệu này là xác nhận đáp ứng toàn bộ pháp luật.</p>' if draft else ''
    html = f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>{escape(title)} · JinHunt</title><link rel="stylesheet" href="/static/legal.css"><script src="/static/legal.js" defer></script></head><body><header><a href="/" class="legal-brand">◈ JinHunt</a><a href="/">← Về bảng tin</a></header><nav aria-label="Chính sách"><a href="/terms">Điều khoản</a><a href="/privacy">Quyền riêng tư</a><a href="/copyright">Bản quyền</a><a href="/support">Gửi yêu cầu</a></nav><main>{banner}<p class="eyebrow">PHIÊN BẢN {VERSION} · CẬP NHẬT 19/10/2026</p><h1>{escape(title)}</h1><p class="legal-intro">{escape(intro)}</p><details class="operator-info"><summary>Thông tin bên vận hành và dữ liệu</summary><dl>{metadata}</dl></details><article>{body}</article></main><footer>JinHunt · Tôn trọng sáng tạo, bảo vệ quyền riêng tư.<br><a href="/support">Yêu cầu hỗ trợ / bản quyền / dữ liệu cá nhân</a></footer></body></html>'''
    return HTMLResponse(html,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer","X-Content-Type-Options":"nosniff"})

class TokenInput(BaseModel):
    token: str = Field(min_length=32,max_length=100)

class GuardianApproval(TokenInput):
    legal_version: Literal[VERSION]
    terms_accepted: StrictBool
    privacy_accepted: StrictBool
    guardian_name: str = Field(min_length=2,max_length=150)
    display_name: str = Field(min_length=2,max_length=80)
    guardian_birth_date: date
    relationship: Literal["mother","father","legal_guardian"]
    authority_confirmed: StrictBool
    child_assent_confirmed: StrictBool
    new_password: str = Field(min_length=8,max_length=128)

    @model_validator(mode="after")
    def check_adult(self):
        if age(self.guardian_birth_date) < 18 or self.guardian_birth_date < date(1900,1,1):
            raise ValueError("Người đại diện phải từ đủ 18 tuổi.")
        if not self.guardian_name.strip() or not self.display_name.strip() or not all([self.terms_accepted,self.privacy_accepted,self.authority_confirmed]):
            raise ValueError("Người đại diện cần xác nhận tư cách, điều khoản và xử lý dữ liệu.")
        return self

class SupportInput(BaseModel):
    kind: Literal["copyright","privacy","safety","access","deletion","withdrawal"]
    email: str = Field(max_length=254)
    name: str = Field(min_length=2,max_length=150)
    content_url: str = Field(default="",max_length=500)
    details: str = Field(min_length=20,max_length=4000)
    contact_consent: StrictBool

    @field_validator("email")
    @classmethod
    def clean_mail(cls, value): return email_address(value)

    @model_validator(mode="after")
    def valid(self):
        if not self.contact_consent or len(self.details.strip()) < 20 or len(self.name.strip()) < 2:
            raise ValueError("Hãy nêu yêu cầu rõ ràng và đồng ý xử lý thông tin để tiếp nhận yêu cầu.")
        return self

def build_router(current_user, password_hash):
    router = APIRouter()

    @router.get("/api/legal")
    def legal_config():
        info = operator_info()
        return {"version":VERSION,"draft":not all(info.values()),"operator":info,
                "guardian_email_available":bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))}

    @router.get("/terms",include_in_schema=False)
    def terms(): return legal_page(*DOCUMENTS["terms"])

    @router.get("/privacy",include_in_schema=False)
    def privacy(): return legal_page(*DOCUMENTS["privacy"])

    @router.get("/copyright",include_in_schema=False)
    def copyright(): return legal_page(*DOCUMENTS["copyright"])

    @router.get("/support",include_in_schema=False)
    def support():
        return legal_page("Gửi yêu cầu / phản ánh","Không cần tài khoản. Không gửi mật khẩu, token hoặc giấy tờ nhạy cảm trong biểu mẫu.", '''<form id="support-form"><label>Loại yêu cầu<select name="kind"><option value="copyright">Bản quyền</option><option value="privacy">Hình ảnh / quyền riêng tư</option><option value="safety">An toàn / vi phạm</option><option value="access">Truy cập / nhận bản sao dữ liệu</option><option value="deletion">Xóa dữ liệu / tài khoản</option><option value="withdrawal">Rút lại đồng ý / hạn chế xử lý</option></select></label><label>Họ tên hoặc tên bên có quyền<input name="name" required minlength="2" maxlength="150" autocomplete="name"></label><label>Email để liên hệ<input name="email" type="email" required maxlength="254" autocomplete="email"></label><label>Đường dẫn bài/ảnh hoặc mã tài khoản liên quan<input name="content_url" maxlength="500"></label><label>Mô tả quyền, tư cách đại diện, yêu cầu và bằng chứng phù hợp<textarea name="details" required minlength="20" maxlength="4000"></textarea></label><label class="check"><input type="checkbox" name="contact_consent" required><span>Tôi cung cấp thông tin trung thực và đồng ý xử lý các thông tin này để tiếp nhận, xác minh và giải quyết yêu cầu theo <a href="/privacy" target="_blank" rel="noopener">Chính sách quyền riêng tư</a>.</span></label><button type="submit">Gửi yêu cầu</button><p class="form-status" role="status" aria-live="polite"></p></form><p>Hệ thống chỉ xác nhận việc lưu yêu cầu. Nhân sự vận hành cần kiểm tra và xử lý; yêu cầu không tự động gỡ bài hoặc xóa dữ liệu.</p>''')

    @router.get("/guardian-consent",include_in_schema=False)
    def guardian_page():
        return legal_page("Xác nhận người đại diện","Liên kết chỉ gửi cho người có quyền quản lý hộp thư. Không chia sẻ liên kết hoặc mật khẩu quản lý.",'''<p id="guardian-summary" role="status">Đang kiểm tra liên kết…</p><form id="guardian-form" hidden><label>Họ và tên người đại diện<input name="guardian_name" required minlength="2" maxlength="150" autocomplete="name"></label><label>Ngày sinh người đại diện<input name="guardian_birth_date" type="date" required></label><label>Quan hệ đại diện<select name="relationship"><option value="mother">Mẹ</option><option value="father">Cha</option><option value="legal_guardian">Người đại diện hợp pháp khác</option></select></label><label>Đặt mật khẩu quản lý tài khoản<input name="new_password" type="password" minlength="8" maxlength="128" required autocomplete="new-password"></label><p>Email của bạn trở thành email quản lý/đăng nhập. Mật khẩu cũ (nếu có) sẽ bị thay thế, mọi phiên cũ bị thu hồi. Đây là tài khoản do người đại diện quản lý, không phải tài khoản riêng tự quản của trẻ.</p><label class="check"><input name="authority_confirmed" type="checkbox" required><span>Tôi từ đủ 18 tuổi, là người có quyền đại diện hợp pháp và sẽ quản lý tài khoản, nội dung và thời gian chơi.</span></label><label class="check" id="child-assent-row"><input name="child_assent_confirmed" type="checkbox"><span>Người chơi từ đủ 7 tuổi đã được giải thích phù hợp và đồng ý việc xử lý dữ liệu cần thiết. Tôi xác nhận thông tin này là đúng.</span></label><label class="check"><input name="terms_accepted" type="checkbox" required><span>Tôi đã đọc và chấp nhận <a href="/terms" target="_blank" rel="noopener">Điều khoản sử dụng</a> và <a href="/copyright" target="_blank" rel="noopener">quy tắc bản quyền</a>.</span></label><label class="check"><input name="privacy_accepted" type="checkbox" required><span>Tôi đồng ý xử lý dữ liệu cần thiết cho tài khoản được quản lý theo <a href="/privacy" target="_blank" rel="noopener">Chính sách quyền riêng tư</a>. Không bao gồm quảng cáo/theo dõi hay công bố thông tin nhận diện trẻ em.</span></label><button type="submit">Xác nhận & thiết lập tài khoản quản lý</button><p class="form-status" role="status" aria-live="polite"></p></form><p>Email chỉ xác nhận quyền truy cập hộp thư, chưa xác minh danh tính hoặc quan hệ pháp lý. Không chấp thuận nếu bạn không có quyền đại diện.</p>''')

    def invite_for(db, raw):
        invite = db.scalar(select(GuardianInvite).where(GuardianInvite.token_hash == hashlib.sha256(raw.encode()).hexdigest()).with_for_update())
        if not invite or invite.used_at or invite.expires_at < time.time():
            raise HTTPException(400,"Liên kết không hợp lệ, đã dùng hoặc đã hết hạn.")
        user = db.get(User,invite.user_id)
        if user.account_status != "pending_guardian": raise HTTPException(400,"Tài khoản không còn chờ xác nhận này.")
        return invite,user

    @router.post("/api/guardian/preview")
    def preview(data: TokenInput, db=Depends(get_db)):
        invite,user = invite_for(db,data.token)
        return {"username":user.username,"requires_child_assent":age(user.player_birth_date)>=7,"version":VERSION}

    @router.post("/api/guardian/approve")
    def approve(data: GuardianApproval, db=Depends(get_db)):
        invite,user = invite_for(db,data.token)
        if age(user.player_birth_date)>=7 and not data.child_assent_confirmed:
            raise HTTPException(400,"Cần xác nhận đã có sự đồng ý của người chơi từ đủ 7 tuổi.")
        if db.scalar(select(User.id).where(User.email == invite.guardian_email, User.id != user.id)):
            raise HTTPException(409,"Email người đại diện đã quản lý một tài khoản khác. Hãy gửi yêu cầu hỗ trợ để liên kết phù hợp.")
        claimed = db.execute(update(GuardianInvite).where(GuardianInvite.token_hash==invite.token_hash,GuardianInvite.used_at.is_(None)).values(used_at=time.time()))
        if claimed.rowcount != 1: raise HTTPException(400,"Liên kết đã được sử dụng.")
        user.email, user.phone = invite.guardian_email, None
        user.display_name, user.bio = data.display_name.strip(), ""
        user.password_hash = password_hash(data.new_password)
        user.account_status, user.guardian_managed = "active",1
        db.execute(delete(Token).where(Token.user_id==user.id))
        record_consent(db,user,"guardian",guardian_name=data.guardian_name.strip(),guardian_birth_date=data.guardian_birth_date,
                       relationship=data.relationship,child_assent=int(data.child_assent_confirmed))
        invite.used_at = time.time()
        try: db.commit()
        except IntegrityError:
            db.rollback(); raise HTTPException(409,"Email người đại diện đã được sử dụng. Hãy gửi yêu cầu hỗ trợ.")
        return {"status":"approved","message":"Đã thiết lập tài khoản được quản lý. Người đại diện đăng nhập bằng email nhận liên kết và mật khẩu vừa đặt."}

    @router.post("/api/me/legal-consent")
    def accept(data: ConsentInput, user=Depends(current_user), db=Depends(get_db)):
        if user.player_birth_date and data.player_birth_date != user.player_birth_date:
            raise HTTPException(409,"Không thể đổi ngày sinh trong bước đồng ý. Hãy gửi yêu cầu chỉnh sửa dữ liệu.")
        user.player_birth_date = data.player_birth_date
        if age(data.player_birth_date)<18 or user.guardian_managed:
            start_guardian(db,user,data.guardian_email or user.email)
            db.commit()
            return {"status":"pending_guardian","message":"Yêu cầu đã gửi đến email người đại diện. Phiên hiện tại đã đóng; chỉ dùng lại sau khi xác nhận."}
        if not latest_consent(db,user): record_consent(db,user)
        db.commit()
        return {"status":"accepted"}

    @router.post("/api/me/withdraw-consent")
    def withdraw(user=Depends(current_user), db=Depends(get_db)):
        for consent in db.scalars(select(LegalConsent).where(LegalConsent.user_id==user.id,LegalConsent.withdrawn_at.is_(None))): consent.withdrawn_at=time.time()
        user.account_status="withdrawn"
        db.execute(delete(Token).where(Token.user_id==user.id))
        db.commit()
        return {"status":"withdrawn","message":"Đã dừng tài khoản và thu hồi phiên đăng nhập. Dữ liệu chưa tự động xóa; dùng biểu mẫu hỗ trợ để yêu cầu xóa hoặc xử lý tiếp."}

    @router.post("/api/legal/requests",status_code=201)
    def support_request(data: SupportInput, db=Depends(get_db)):
        recent = db.scalar(select(func.count()).select_from(LegalRequest).where(LegalRequest.email==data.email,LegalRequest.created_at>time.time()-3600))
        if recent>=5: raise HTTPException(429,"Email này đã gửi 5 yêu cầu trong một giờ. Vui lòng chờ hoặc liên hệ đầu mối vận hành.")
        reference=secrets.token_hex(12)
        db.add(LegalRequest(reference=reference,kind=data.kind,email=data.email,name=data.name.strip(),content_url=data.content_url.strip(),details=data.details.strip(),created_at=time.time(),legal_version=VERSION))
        db.commit()
        return {"reference":reference,"status":"received","message":"Đã lưu yêu cầu để người vận hành xử lý. Hãy giữ mã tham chiếu; đây chưa phải xác nhận đã gỡ/xóa nội dung."}

    return router
