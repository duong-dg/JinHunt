import hashlib
from types import SimpleNamespace
import pyotp
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_game import client, account
from app.main import app
from app.database import get_db
from app.models import User, Token, LoginBucket
from app import auth_security

def enroll(client,monkeypatch,username='securestaff'):
    monkeypatch.setenv('STAFF_TOTP_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('STAFF_COOKIE_SECURE','0')
    clock=SimpleNamespace(time=lambda:1800000000)
    monkeypatch.setattr(auth_security,'time',clock)
    headers=account(client,username)
    secret=pyotp.random_base32()
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try:
        user=db.scalar(select(User).where(User.username==username))
        user.role='admin';user.staff_totp_secret=auth_security.secret_cipher().encrypt(secret.encode()).decode();db.commit()
    finally: generator.close()
    return headers,pyotp.TOTP(secret).at(clock.time()),secret

def test_staff_requires_separate_login_otp_and_cookie_csrf(client,monkeypatch):
    old,code,secret=enroll(client,monkeypatch)
    assert client.get('/api/moderation/queue',headers=old).status_code==401
    assert client.post('/api/auth/login',json={'username':'securestaff','password':'test-password-123'}).status_code==403
    data={'username':'securestaff','password':'test-password-123','otp':code}
    assert client.post('/api/staff/login',json=data).status_code==403
    wrong='1'+code[1:] if code[0]!='1' else '2'+code[1:]
    assert client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json={**data,'otp':wrong}).status_code==401
    result=client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json=data)
    assert result.status_code==200,result.text
    assert 'token' not in result.json() and secret not in result.text
    cookie=result.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Max-Age=28800' in cookie
    assert client.get('/api/staff/session').json()['role']=='admin'
    assert client.get('/api/moderation/queue').status_code==200
    assert client.post('/api/moderation/images/decision',json={'image_url':'/uploads/missing.jpg','action':'remove','reason':'Review reason'}).status_code==403
    assert client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json=data).status_code==401 # replay
    assert client.post('/api/staff/logout').status_code==403
    assert client.post('/api/staff/logout',headers={'X-JinHunt-Staff':'1'}).status_code==200
    assert client.get('/api/moderation/queue').status_code==401

def test_staff_https_required_and_ordinary_user_cannot_enter(client,monkeypatch):
    _,code,_=enroll(client,monkeypatch)
    monkeypatch.setenv('STAFF_COOKIE_SECURE','1')
    data={'username':'securestaff','password':'test-password-123','otp':code}
    result=client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json=data)
    assert result.status_code==426
    monkeypatch.setenv('STAFF_COOKIE_SECURE','0')
    normal=account(client,'ordinary')
    assert client.get('/api/staff/session',headers=normal).status_code==403
    assert client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json={**data,'username':'ordinary'}).status_code==401

def test_login_throttle_persists_across_requests_and_aliases(client,monkeypatch):
    account(client,'ratelimited')
    for index in range(8):
        identifier='ratelimited' if index%2 else 'ratelimited@example.com'
        assert client.post('/api/auth/login',json={'username':identifier,'password':'wrong-password'}).status_code==401
    blocked=client.post('/api/auth/login',json={'username':'ratelimited','password':'test-password-123'})
    assert blocked.status_code==429 and int(blocked.headers['retry-after'])>0
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try: assert db.scalar(select(LoginBucket.key).limit(1))
    finally: generator.close()

def test_secure_cookie_expiry_and_revocation(client,monkeypatch):
    _,code,_=enroll(client,monkeypatch)
    monkeypatch.setenv('STAFF_COOKIE_SECURE','1')
    # Use HTTPS for this one request so the secure cookie is issued.
    response=client.post('https://testserver/api/staff/login',headers={'X-JinHunt-Staff':'1'},json={'username':'securestaff','password':'test-password-123','otp':code})
    assert response.status_code==200 and 'Secure' in response.headers['set-cookie']
    cookie=response.cookies.get(auth_security.COOKIE_NAME)
    assert client.get('https://testserver/api/moderation/queue').status_code==200
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try:
        row=db.get(Token,hashlib.sha256(cookie.encode()).hexdigest());row.expires_at=0;db.commit()
    finally: generator.close()
    assert client.get('https://testserver/api/moderation/queue').status_code==401
    assert client.get('https://testserver/api/cases').status_code==200 # stale staff cookie must not break public feed

def test_staff_without_enrollment_stays_blocked(client,monkeypatch):
    monkeypatch.setenv('STAFF_COOKIE_SECURE','0')
    headers=account(client,'unenrolled')
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try:
        user=db.scalar(select(User).where(User.username=='unenrolled'));user.role='moderator';db.commit()
    finally: generator.close()
    assert client.get('/api/moderation/queue',headers=headers).status_code==401
    assert client.post('/api/staff/login',headers={'X-JinHunt-Staff':'1'},json={'username':'unenrolled','password':'test-password-123','otp':'123456'}).status_code==401
