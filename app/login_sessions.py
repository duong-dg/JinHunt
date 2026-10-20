"""First-party session history. Client IP comes from ASGI, not arbitrary headers."""
import hashlib
import ipaddress
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from .models import LoginSession, Token


def client_ip(request):
    try:return str(ipaddress.ip_address(request.client.host)) if request and request.client else None
    except ValueError:return None


def record_session(db,request,token,known_login=True):
    now=time.time()
    entry=LoginSession(id=secrets.token_hex(16),user_id=token.user_id,token_hash=token.token_hash,login_at=now if known_login else None,last_seen_at=now,expires_at=token.expires_at,ip_address=client_ip(request),user_agent=(request.headers.get('user-agent','') if request else '')[:500])
    db.add(entry)
    return entry


def touch_session(db,request,token):
    row=db.scalar(select(LoginSession).where(LoginSession.token_hash==token.token_hash))
    if not row:
        try:
            with db.begin_nested():record_session(db,request,token,False);db.flush()
            db.commit()
        except IntegrityError:pass
    elif row.last_seen_at<time.time()-300:
        row.last_seen_at=time.time();db.commit()


def device_name(agent):
    agent=agent.lower()
    platform='iPad' if 'ipad' in agent else 'iPhone' if 'iphone' in agent else 'Android' if 'android' in agent else 'Windows' if 'windows' in agent else 'Mac' if 'macintosh' in agent else 'Linux' if 'linux' in agent else 'Thiết bị chưa xác định'
    browser='Edge' if 'edg' in agent else 'Firefox' if 'firefox' in agent or 'fxios' in agent else 'Chrome' if 'chrome' in agent or 'crios' in agent else 'Safari' if 'safari' in agent else 'Trình duyệt'
    return f'{browser} · {platform}'


def build_router(current_user):
    router=APIRouter()
    def current_hash(request):
        auth=request.headers.get('authorization','')
        raw=auth[7:] if auth.startswith('Bearer ') else request.cookies.get('jinhunt_staff','')
        return hashlib.sha256(raw.encode()).hexdigest()

    @router.get('/api/me/sessions')
    def sessions(request:Request,offset:int=0,user=Depends(current_user),db:Session=Depends(get_db)):
        if offset<0:raise HTTPException(400,'Trang không hợp lệ.')
        now=time.time();own=current_hash(request)
        rows=db.execute(select(LoginSession,Token.token_hash).outerjoin(Token,Token.token_hash==LoginSession.token_hash).where(LoginSession.user_id==user.id).order_by((LoginSession.token_hash==own).desc(),LoginSession.last_seen_at.desc(),LoginSession.id).offset(offset).limit(31)).all()
        items=[]
        for row,token in rows[:30]:
            active=bool(token and row.expires_at>now)
            private=bool(row.ip_address and ipaddress.ip_address(row.ip_address).is_private)
            items.append({'id':row.id,'device':device_name(row.user_agent),'ip_address':row.ip_address,'location':'Mạng nội bộ' if private else 'Chưa xác định địa điểm','login_at':row.login_at,'last_seen_at':row.last_seen_at,'expires_at':row.expires_at,'ended_at':row.ended_at,'active':active,'is_current':active and row.token_hash==own})
        return {'items':items,'next_offset':offset+30 if len(rows)>30 else None}

    @router.delete('/api/me/sessions/{session_id}')
    def revoke(session_id:str,user=Depends(current_user),db:Session=Depends(get_db)):
        row=db.scalar(select(LoginSession).where(LoginSession.id==session_id,LoginSession.user_id==user.id))
        if not row:raise HTTPException(404,'Không tìm thấy phiên đăng nhập.')
        db.execute(delete(Token).where(Token.token_hash==row.token_hash,Token.user_id==user.id))
        row.ended_at=time.time();db.commit()
        return {'message':'Đã đăng xuất thiết bị.'}

    @router.post('/api/me/sessions/revoke-others')
    def revoke_others(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        own=current_hash(request)
        db.execute(delete(Token).where(Token.user_id==user.id,Token.token_hash!=own))
        db.execute(update(LoginSession).where(LoginSession.user_id==user.id,LoginSession.token_hash!=own,LoginSession.ended_at.is_(None)).values(ended_at=time.time()))
        db.commit();return {'message':'Đã đăng xuất các thiết bị khác.'}
    return router
