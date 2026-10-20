"""Email OTP password recovery; staff authentication remains separate."""
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Token, EmailVerification
from .auth_security import throttle
from .email_verification import issue_code, verify_code


def build_router(clean_email,password_hash):
    router=APIRouter()
    class Address(BaseModel):
        email:str=Field(min_length=3,max_length=254)
        @field_validator('email')
        @classmethod
        def address(cls,value):
            result=clean_email(value)
            if not result:raise ValueError('Nhập email hợp lệ.')
            return result
    class Reset(BaseModel):
        challenge_id:str=Field(min_length=16,max_length=64)
        code:str=Field(pattern=r'^[0-9]{6}$')
        new_password:str=Field(min_length=8,max_length=128)

    @router.post('/api/auth/password-reset/request')
    def request_reset(data:Address,request:Request,db:Session=Depends(get_db)):
        person=db.scalar(select(User).where(User.email==data.email,User.email_verified==1,User.account_status=='active',User.suspended==0,User.role=='user'))
        result={'challenge_id':secrets.token_urlsafe(24),'expires_in':600,'retry_after':60}
        if person:
            try:
                issued=issue_code(db,data.email,'password_reset',person.id,request)
                result['challenge_id']=issued['challenge_id']
            except HTTPException as error:
                if error.status_code!=503:raise
                db.rollback()
                # SMTP failure must not reveal whether an account exists.
                import logging
                logging.getLogger(__name__).warning('Password recovery email could not be sent; check SMTP configuration.')
        else:
            throttle(db,'email-ip',request.client.host if request.client else 'unknown',20)
            throttle(db,'email-minute',data.email,1,window=60)
            throttle(db,'email-hour',data.email,5,window=3600)
        return {**result,'message':'Nếu email đã được xác minh cho tài khoản hợp lệ, bạn sẽ nhận mã đặt lại mật khẩu. Kiểm tra cả thư rác.'}

    @router.post('/api/auth/password-reset/confirm')
    def confirm_reset(data:Reset,request:Request,db:Session=Depends(get_db)):
        throttle(db,'password-reset-confirm',request.client.host if request.client else 'unknown',50)
        original=db.get(EmailVerification,data.challenge_id)
        row=verify_code(db,data.challenge_id,data.code,'password_reset',original.user_id if original else None)
        person=db.get(User,row.user_id)
        if not person or person.email!=row.email or not person.email_verified or person.role!='user' or person.account_status!='active' or person.suspended:
            raise HTTPException(400,'Mã không còn hợp lệ cho tài khoản này.')
        claimed=db.execute(update(EmailVerification).where(EmailVerification.id==row.id,EmailVerification.consumed_at.is_(None),EmailVerification.expires_at>time.time()).values(consumed_at=time.time())).rowcount
        if not claimed:raise HTTPException(400,'Mã đã dùng hoặc hết hạn.')
        person.password_hash=password_hash(data.new_password)
        db.execute(delete(Token).where(Token.user_id==person.id))
        db.execute(update(EmailVerification).where(EmailVerification.purpose=='password_reset',EmailVerification.user_id==person.id).values(expires_at=0))
        db.commit()
        return {'message':'Đã đổi mật khẩu và đăng xuất các phiên cũ. Hãy đăng nhập lại.'}
    return router
