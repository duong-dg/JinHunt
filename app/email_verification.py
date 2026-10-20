import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, EmailVerification
from .auth_security import throttle

def code_digest(reference,email,purpose,code):
    key=os.getenv('EMAIL_CODE_KEY') or os.getenv('SMTP_PASSWORD')
    if not key: raise HTTPException(503,'Chưa cấu hình khóa bảo vệ mã xác minh email.')
    return hmac.new(key.encode(),f'{reference}:{email}:{purpose}:{code}'.encode(),hashlib.sha256).hexdigest()

def send_code(email,code,link=None):
    host,sender=os.getenv('SMTP_HOST'),os.getenv('SMTP_FROM')
    if not host or not sender: raise HTTPException(503,'Chưa cấu hình SMTP để gửi mã xác minh.')
    message=EmailMessage();message['From']=sender;message['To']=email;message['Subject']='JinHunt — Mã xác minh'
    message.set_content(f'Mã xác minh JinHunt của bạn: {code}\n\nMã hết hạn sau 10 phút, chỉ dùng một lần. Không chia sẻ mã cho người khác. Nếu bạn không yêu cầu mã này, hãy bỏ qua email.')
    if link:
        message.set_content(message.get_content()+f'\nHoặc mở liên kết này để xác minh đăng ký:\n{link}\n\nChỉ xác nhận nếu chính bạn đang tạo tài khoản JinHunt. Không chuyển tiếp liên kết cho người khác.\n')
    try:
        mode=os.getenv('SMTP_SECURITY','starttls')
        if mode not in {'ssl','starttls'}: raise ValueError('TLS required')
        port=int(os.getenv('SMTP_PORT','465' if mode=='ssl' else '587'))
        smtp=smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) if mode=='ssl' else smtplib.SMTP(host,port,timeout=20)
        with smtp:
            if mode=='starttls': smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
            smtp.send_message(message)
    except Exception:
        raise HTTPException(503,'Chưa gửi được mã xác minh. Hãy thử lại sau; email chưa được đánh dấu xác minh.')

def issue_code(db,email,purpose,user_id,request):
    throttle(db,'email-ip',request.client.host if request.client else 'unknown',20)
    throttle(db,'email-minute',email,1,window=60)
    throttle(db,'email-hour',email,5,window=3600)
    now=time.time();reference=secrets.token_urlsafe(24);code=f'{secrets.randbelow(1000000):06d}'
    digest=code_digest(reference,email,purpose,code)
    # Resending invalidates the previous code/proof for this exact flow, not other users.
    db.execute(update(EmailVerification).where(EmailVerification.email==email,EmailVerification.purpose==purpose,EmailVerification.user_id==user_id,EmailVerification.consumed_at.is_(None)).values(expires_at=0))
    base=os.getenv('PUBLIC_BASE_URL','').rstrip('/');parsed=urlparse(base)
    link_token=secrets.token_urlsafe(32) if purpose=='register' and parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.query and not parsed.fragment else None
    link=base+'/verify-email#token='+link_token if link_token else None
    row=EmailVerification(id=reference,email=email,purpose=purpose,user_id=user_id,code_hash=digest,link_hash=hashlib.sha256(link_token.encode()).hexdigest() if link_token else None,created_at=now,expires_at=now+600)
    db.add(row);db.flush();send_code(email,code,link);db.commit()
    return {'challenge_id':reference,'expires_in':600,'retry_after':60,'has_link':bool(link),'message':'Đã gửi mã 6 số'+(' và liên kết xác minh' if link else '')+' đến email. Kiểm tra cả thư rác.'}

def registration_result(db,row):
    raw=secrets.token_urlsafe(32);row.proof_hash=hashlib.sha256(raw.encode()).hexdigest();db.commit()
    return {'verification_token':raw,'challenge_id':row.id,'email':row.email,'expires_at':row.expires_at,'message':'Email đã xác minh. Bạn có thể hoàn tất đăng ký.'}

def verify_code(db,reference,code,purpose,user_id):
    now=time.time()
    count=db.execute(update(EmailVerification).where(EmailVerification.id==reference,EmailVerification.purpose==purpose,EmailVerification.user_id==user_id,EmailVerification.verified_at.is_(None),EmailVerification.expires_at>now,EmailVerification.attempts<5).values(attempts=EmailVerification.attempts+1)).rowcount
    if not count: raise HTTPException(400,'Mã đã hết hạn, đã dùng hoặc thử sai quá nhiều lần. Hãy yêu cầu mã mới.')
    row=db.get(EmailVerification,reference,populate_existing=True)
    if not hmac.compare_digest(row.code_hash,code_digest(reference,row.email,purpose,code)):
        db.commit();raise HTTPException(400,'Mã xác minh chưa đúng. Mỗi mã được thử tối đa 5 lần.')
    row.verified_at=now
    return row

def consume_registration_proof(db,email,proof):
    if not proof: raise HTTPException(400,'Hãy xác minh email bằng mã gửi đến hộp thư trước khi tạo tài khoản.')
    claimed=db.execute(update(EmailVerification).where(EmailVerification.email==email,EmailVerification.purpose=='register',EmailVerification.proof_hash==hashlib.sha256(proof.encode()).hexdigest(),EmailVerification.verified_at.is_not(None),EmailVerification.consumed_at.is_(None),EmailVerification.expires_at>time.time()).values(consumed_at=time.time())).rowcount
    if not claimed: raise HTTPException(400,'Xác minh email đã hết hạn, không khớp hoặc đã dùng. Hãy yêu cầu mã mới.')

def build_router(current_user,clean_email,private_user):
    router=APIRouter()
    class Address(BaseModel):
        email:str=Field(min_length=3,max_length=254)
        @field_validator('email')
        @classmethod
        def valid_email(cls,value):
            email=clean_email(value)
            if not email: raise ValueError('Nhập email hợp lệ.')
            return email
    class Code(BaseModel):
        challenge_id:str=Field(min_length=16,max_length=64)
        code:str=Field(pattern=r'^[0-9]{6}$')
    class Link(BaseModel):
        token:str=Field(min_length=32,max_length=128)

    @router.post('/api/email-verification/request')
    def request_registration(data:Address,request:Request,db:Session=Depends(get_db)):
        return issue_code(db,data.email,'register',None,request)

    @router.post('/api/email-verification/confirm')
    def confirm_registration(data:Code,request:Request,db:Session=Depends(get_db)):
        throttle(db,'email-confirm-ip',request.client.host if request.client else 'unknown',50)
        row=verify_code(db,data.challenge_id,data.code,'register',None)
        return registration_result(db,row)

    @router.post('/api/email-verification/link')
    def confirm_link(data:Link,request:Request,db:Session=Depends(get_db)):
        throttle(db,'email-confirm-ip',request.client.host if request.client else 'unknown',50)
        digest=hashlib.sha256(data.token.encode()).hexdigest();now=time.time()
        result=db.execute(update(EmailVerification).where(EmailVerification.link_hash==digest,EmailVerification.purpose=='register',EmailVerification.verified_at.is_(None),EmailVerification.expires_at>now,EmailVerification.attempts<5).values(verified_at=now)).rowcount
        if not result: raise HTTPException(400,'Liên kết đã hết hạn, đã dùng hoặc không hợp lệ. Hãy yêu cầu mã mới.')
        row=db.scalar(select(EmailVerification).where(EmailVerification.link_hash==digest))
        return registration_result(db,row)

    @router.post('/api/me/email-verification/request')
    def request_change(data:Address,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        if user.guardian_managed: raise HTTPException(403,'Email người đại diện cần đổi qua hỗ trợ để kiểm tra quyền quản lý.')
        if db.scalar(select(User.id).where(User.email==data.email,User.id!=user.id)):
            raise HTTPException(409,'Email đã được tài khoản khác sử dụng.')
        return issue_code(db,data.email,'change',user.id,request)

    @router.post('/api/me/email-verification/confirm')
    def confirm_change(data:Code,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        if user.guardian_managed: raise HTTPException(403,'Liên hệ hỗ trợ để đổi email người đại diện.')
        throttle(db,'email-confirm-ip',request.client.host if request.client else 'unknown',50)
        row=verify_code(db,data.challenge_id,data.code,'change',user.id)
        user.email=row.email;user.email_verified=1;row.consumed_at=time.time()
        try: db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Email đã được tài khoản khác sử dụng.')
        return private_user(user,db)
    return router
