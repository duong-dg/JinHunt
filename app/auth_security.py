"""Database-backed throttling shared by workers; encrypted staff TOTP secrets."""
import hashlib
import hmac
import os
import time
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, update
from .models import LoginBucket, User

COOKIE_NAME='jinhunt_staff'

def secret_cipher():
    try:
        return Fernet(os.environ['STAFF_TOTP_KEY'].encode())
    except (KeyError,ValueError):
        raise HTTPException(503,'Chưa cấu hình khóa bảo vệ xác thực quản trị trên server.')

def throttle(db,scope,identity,limit,window=900):
    now=time.time();period=int(now//window)
    key=hashlib.sha256(f'{scope}:{identity}:{period}'.encode()).hexdigest()
    if db.get_bind().dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt=insert(LoginBucket).values(key=key,attempts=1,expires_at=(period+1)*window)
    stmt=stmt.on_conflict_do_update(index_elements=['key'],set_={'attempts':LoginBucket.attempts+1}).returning(LoginBucket.attempts)
    count=db.scalar(stmt)
    db.execute(delete(LoginBucket).where(LoginBucket.expires_at<now-900))
    db.commit()
    if count>limit:
        raise HTTPException(429,'Bạn đã thử quá nhiều lần. Vui lòng chờ rồi thử lại.',headers={'Retry-After':str(max(1,int((period+1)*window-now)))})

def login_limits(db,request,identifier):
    # Trust the ASGI client address, never arbitrary X-Forwarded-For headers here.
    throttle(db,'ip',request.client.host if request.client else 'unknown',50)
    throttle(db,'identifier',identifier,8)

def check_password(user,password,password_hash):
    salt=user.password_hash.split(':')[0] if user else '00000000000000000000000000000000'
    candidate=password_hash(password,salt)
    return bool(hmac.compare_digest(candidate,user.password_hash if user else salt+':'+'0'*128) and user)

def consume_totp(db,user,code):
    if not user.staff_totp_secret:
        return False
    try:
        secret=secret_cipher().decrypt(user.staff_totp_secret.encode()).decode()
    except (InvalidToken,UnicodeError):
        raise HTTPException(503,'Không mở được khóa OTP. Liên hệ người vận hành server.')
    totp=pyotp.TOTP(secret)
    counter=int(time.time()//30)
    matched=next((step for step in (counter-1,counter,counter+1) if hmac.compare_digest(totp.generate_otp(step),code)),None)
    if matched is None:
        return False
    # Atomic condition prevents concurrent reuse of the same 30-second code.
    claimed=db.execute(update(User).where(User.id==user.id,User.staff_totp_counter<matched,User.staff_totp_secret==user.staff_totp_secret).values(staff_totp_counter=matched)).rowcount
    return bool(claimed)
