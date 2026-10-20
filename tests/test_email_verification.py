from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from test_game import client, account, email_proof, LEGAL_FIELDS
from app.main import app
from app.database import get_db
from app.models import EmailVerification, User
from app import email_verification, auth_security

def db_read(query):
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try: return db.scalar(query)
    finally: generator.close()

def request_code(client,email,headers=None):
    path='/api/me/email-verification/request' if headers else '/api/email-verification/request'
    response=client.post(path,headers=headers or {},json={'email':email})
    assert response.status_code==200,response.text
    return response.json()['challenge_id'],client.email_codes[-1][1]

def test_registration_requires_email_ownership_and_proof_is_one_use(client):
    data={'username':'verifyowner','password':'test-password-123','email':'verify@example.com',**LEGAL_FIELDS}
    assert client.post('/api/auth/register',json=data).status_code==400
    proof=email_proof(client,data['email'])
    assert client.post('/api/auth/register',json={**data,'email':'different@example.com','email_verification_token':proof}).status_code==400
    response=client.post('/api/auth/register',json={**data,'email_verification_token':proof})
    assert response.status_code==201,response.text
    assert response.json()['user']['email_verified'] is True
    row=db_read(select(EmailVerification).where(EmailVerification.email==data['email']))
    assert row.consumed_at is not None and row.proof_hash!=proof
    assert client.post('/api/email-verification/confirm',json={'challenge_id':row.id,'code':client.email_codes[-1][1]}).status_code==400

def test_wrong_codes_exhaust_after_five_attempts(client):
    reference,code=request_code(client,'five@example.com')
    wrong=('1' if code[0]!='1' else '2')+code[1:]
    for _ in range(5):
        assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':wrong}).status_code==400
    assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':code}).status_code==400
    row=db_read(select(EmailVerification).where(EmailVerification.id==reference))
    assert row.attempts==5 and row.code_hash!=code and row.verified_at is None

def test_expiry_resend_and_rate_limits(client,monkeypatch):
    now=[1800000010.0];clock=SimpleNamespace(time=lambda:now[0])
    monkeypatch.setattr(email_verification,'time',clock);monkeypatch.setattr(auth_security,'time',clock)
    first,old=request_code(client,'resend@example.com')
    assert client.post('/api/email-verification/request',json={'email':'resend@example.com'}).status_code==429
    now[0]+=61
    second,new=request_code(client,'resend@example.com')
    assert client.post('/api/email-verification/confirm',json={'challenge_id':first,'code':old}).status_code==400
    now[0]+=601
    assert client.post('/api/email-verification/confirm',json={'challenge_id':second,'code':new}).status_code==400

def test_email_change_bound_to_user_and_keeps_old_address_until_verified(client):
    owner=account(client,'changeowner');other=account(client,'changeother')
    assert client.patch('/api/me',headers=owner,json={'email':'new@example.com'}).status_code==400
    reference,code=request_code(client,'new@example.com',owner)
    assert client.get('/api/me',headers=owner).json()['email']=='changeowner@example.com'
    assert client.post('/api/me/email-verification/confirm',headers=other,json={'challenge_id':reference,'code':code}).status_code==400
    assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':code}).status_code==400
    result=client.post('/api/me/email-verification/confirm',headers=owner,json={'challenge_id':reference,'code':code})
    assert result.status_code==200,result.text
    assert result.json()['email']=='new@example.com' and result.json()['email_verified'] is True
    assert client.post('/api/me/email-verification/confirm',headers=owner,json={'challenge_id':reference,'code':code}).status_code==400
    assert client.get('/api/me',headers=other).json()['email']=='changeother@example.com'

def test_failed_send_does_not_mark_email_verified(client,monkeypatch):
    def failed(*args): raise HTTPException(503,'SMTP unavailable')
    monkeypatch.setattr(email_verification,'send_code',failed)
    assert client.post('/api/email-verification/request',json={'email':'failure@example.com'}).status_code==503
    assert db_read(select(EmailVerification.id).where(EmailVerification.email=='failure@example.com')) is None

def test_legacy_email_can_be_verified_without_changing_it(client):
    owner=account(client,'legacyemail')
    generator=app.dependency_overrides[get_db]();db=next(generator)
    try:
        user=db.scalar(select(User).where(User.username=='legacyemail'));user.email_verified=0;db.commit()
    finally: generator.close()
    assert client.get('/api/me',headers=owner).json()['email_verified'] is False
    # A different purpose gets its own code flow; recipient cooldown still applies, so advance its window.
    from unittest.mock import patch
    import time
    clock=SimpleNamespace(time=lambda:time.time()+61)
    with patch.object(auth_security,'time',clock):
        reference,code=request_code(client,'legacyemail@example.com',owner)
    result=client.post('/api/me/email-verification/confirm',headers=owner,json={'challenge_id':reference,'code':code})
    assert result.status_code==200 and result.json()['email_verified'] is True

def test_registration_proof_expiry_and_recipient_hour_limit(client,monkeypatch):
    now=[1800000010.0];clock=SimpleNamespace(time=lambda:now[0])
    monkeypatch.setattr(email_verification,'time',clock);monkeypatch.setattr(auth_security,'time',clock)
    proof=email_proof(client,'expireproof@example.com')
    now[0]+=601
    payload={'username':'expiredproof','email':'expireproof@example.com','password':'test-password-123','email_verification_token':proof,**LEGAL_FIELDS}
    assert client.post('/api/auth/register',json=payload).status_code==400
    assert db_read(select(User.id).where(User.username=='expiredproof')) is None
    for _ in range(5):
        request_code(client,'limit@example.com');now[0]+=61
    result=client.post('/api/email-verification/request',json={'email':'limit@example.com'})
    assert result.status_code==429

def test_email_link_alternative_is_explicit_one_use_and_creates_no_account_by_itself(client,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    monkeypatch.setenv('PUBLIC_BASE_URL','https://jinhunt.test')
    reference,code=request_code(client,'link@example.com')
    link=client.email_links[-1]
    assert link.startswith('https://jinhunt.test/verify-email#token=')
    raw=parse_qs(urlparse(link).fragment)['token'][0]
    row=db_read(select(EmailVerification).where(EmailVerification.id==reference))
    assert row.link_hash!=raw and row.verified_at is None
    assert client.get('/verify-email').status_code==200
    assert db_read(select(EmailVerification.verified_at).where(EmailVerification.id==reference)) is None
    result=client.post('/api/email-verification/link',json={'token':raw})
    assert result.status_code==200,result.text
    assert result.headers['cache-control']=='no-store'
    assert db_read(select(User.id).where(User.email=='link@example.com')) is None
    assert client.post('/api/email-verification/link',json={'token':raw}).status_code==400
    assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':code}).status_code==400
    payload={'username':'linkuser','password':'test-password-123','email':'link@example.com','email_verification_token':result.json()['verification_token'],**LEGAL_FIELDS}
    registered=client.post('/api/auth/register',json=payload)
    assert registered.status_code==201 and registered.json()['user']['email_verified']

def test_otp_consumes_link_and_unconfigured_origin_never_uses_request_host(client,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    monkeypatch.setenv('PUBLIC_BASE_URL','https://jinhunt.test')
    reference,code=request_code(client,'otpfirst@example.com')
    raw=parse_qs(urlparse(client.email_links[-1]).fragment)['token'][0]
    assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':code}).status_code==200
    assert client.post('/api/email-verification/link',json={'token':raw}).status_code==400
    monkeypatch.setenv('PUBLIC_BASE_URL','http://not-a-secure-origin.test')
    response=client.post('/api/email-verification/request',headers={'Host':'attacker.example'},json={'email':'nolink@example.com'})
    assert response.status_code==200 and response.json()['has_link'] is False
    assert client.email_links[-1] is None
