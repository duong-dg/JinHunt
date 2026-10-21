from sqlalchemy import select
from test_game import client, account, create_case, staff_account
from app.main import app
from app.database import get_db
from app.models import User, Case, EmailVerification, CommentReport


def request_recovery(client,email):
    # Registration has just sent a code in this fixture; simulate the minute cooldown passing.
    import hashlib,time
    from app.models import LoginBucket
    with next(app.dependency_overrides[get_db]()) as db:
        key=hashlib.sha256(f'email-minute:{email}:{int(time.time()//60)}'.encode()).hexdigest()
        row=db.get(LoginBucket,key)
        if row:db.delete(row);db.commit()
    return client.post('/api/auth/password-reset/request',json={'email':email})


def test_password_recovery_revokes_sessions_and_code_is_single_use(client):
    headers=account(client,'resetplayer')
    request=request_recovery(client,'resetplayer@example.com')
    assert request.status_code==200
    assert request.headers['cache-control']=='no-store'
    reference=request.json()['challenge_id'];code=client.email_codes[-1][1]
    assert client.post('/api/email-verification/confirm',json={'challenge_id':reference,'code':code}).status_code==400
    payload={'challenge_id':reference,'code':code,'new_password':'new-password-123'}
    assert client.post('/api/auth/password-reset/confirm',json=payload).status_code==200
    assert client.get('/api/me',headers=headers).status_code==401
    assert client.post('/api/auth/password-reset/confirm',json=payload).status_code==400
    assert client.post('/api/auth/login',json={'username':'resetplayer','password':'test-password-123'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'resetplayer','password':'new-password-123'}).status_code==200


def test_recovery_unknown_unverified_staff_and_email_changed(client):
    account(client,'reseteligible');account(client,'resetunverified');account(client,'resetstaff')
    with next(app.dependency_overrides[get_db]()) as db:
        db.scalar(select(User).where(User.username=='resetunverified')).email_verified=0
        db.scalar(select(User).where(User.username=='resetstaff')).role='admin';db.commit()
    before=len(client.email_codes)
    for email in ['missing@example.com','resetunverified@example.com','resetstaff@example.com']:
        result=request_recovery(client,email)
        assert result.status_code==200 and set(result.json())=={'challenge_id','expires_in','retry_after','message'}
        assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':result.json()['challenge_id'],'code':'123456','new_password':'new-password-123'}).status_code==400
    assert len(client.email_codes)==before
    result=request_recovery(client,'reseteligible@example.com').json()
    code=client.email_codes[-1][1]
    with next(app.dependency_overrides[get_db]()) as db:
        db.scalar(select(User).where(User.username=='reseteligible')).email='different@example.com';db.commit()
    assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':result['challenge_id'],'code':code,'new_password':'new-password-123'}).status_code==400


def test_recovery_wrong_attempts_and_expiry(client):
    account(client,'resetattempt')
    request=request_recovery(client,'resetattempt@example.com').json()
    code=client.email_codes[-1][1];bad='000000' if code!='000000' else '111111'
    for _ in range(5):assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':request['challenge_id'],'code':bad,'new_password':'new-password-123'}).status_code==400
    assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':request['challenge_id'],'code':code,'new_password':'new-password-123'}).status_code==400
    account(client,'resetexpired')
    request=request_recovery(client,'resetexpired@example.com').json();code=client.email_codes[-1][1]
    with next(app.dependency_overrides[get_db]()) as db:db.get(EmailVerification,request['challenge_id']).expires_at=0;db.commit()
    assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':request['challenge_id'],'code':code,'new_password':'new-password-123'}).status_code==400


def test_profiles_follows_bookmarks_and_search(client,monkeypatch):
    owner=account(client,'communityowner');viewer=account(client,'communityviewer')
    post=create_case(client,owner);uid=post['creator_id'];cid=post['id']
    public=client.get(f'/api/users/{uid}').json()
    assert not {'email','phone','password_hash','player_birth_date'} & set(public)
    assert public['post_count']==1
    for _ in range(2):assert client.put(f'/api/users/{uid}/follow',headers=viewer).status_code==200
    assert client.get(f'/api/users/{uid}',headers=viewer).json()['followers']==1
    assert client.get(f'/api/users/{uid}',headers=viewer).json()['followed_by_me'] is True
    assert len(client.get(f'/api/users/{uid}/followers').json())==1
    assert len(client.get('/api/cases?following=true',headers=viewer).json())==1
    assert client.get('/api/cases?following=true').status_code==401
    assert client.put(f'/api/users/{uid}/follow',headers=owner).status_code==400
    for _ in range(2):assert client.put(f'/api/cases/{cid}/bookmark',headers=viewer).status_code==200
    assert client.get('/api/me/bookmarks').status_code==401
    assert len(client.get('/api/me/bookmarks',headers=viewer).json())==1
    assert client.get('/api/me/bookmarks',headers=owner).json()==[]
    assert client.get(f'/api/cases/{cid}',headers=viewer).json()['bookmarked_by_me'] is True
    assert len(client.get('/api/cases?q=Góc').json())==1
    assert client.get('/api/cases?q=Chợ Bến Thành').json()==[]
    assert client.get('/api/cases?q=%25').json()==[]
    monkeypatch.setenv('MODERATION_REQUIRE_REVIEW','1');pending=create_case(client,owner)
    assert len(client.get(f'/api/users/{uid}/cases').json())==1
    assert client.put(f'/api/cases/{pending["id"]}/bookmark',headers=viewer).status_code==404
    client.delete(f'/api/cases/{cid}/bookmark',headers=viewer)
    client.delete(f'/api/users/{uid}/follow',headers=viewer)
    assert client.get('/api/me/bookmarks',headers=viewer).json()==[]
    assert client.get(f'/api/users/{uid}').json()['followers']==0


def test_blocks_hide_content_and_prevent_interaction_both_ways(client):
    owner=account(client,'blockowner');other=account(client,'blockother')
    own=create_case(client,owner);theirs=create_case(client,other);uid=theirs['creator_id']
    client.post(f'/api/cases/{own["id"]}/comments',headers=other,json={'content':'Beautiful place'})
    client.put(f'/api/users/{uid}/follow',headers=owner)
    client.put(f'/api/users/{own["creator_id"]}/follow',headers=other)
    client.put(f'/api/cases/{theirs["id"]}/bookmark',headers=owner)
    assert client.put(f'/api/users/{uid}/block',headers=owner).status_code==200
    assert client.get('/api/me/blocks',headers=owner).json()[0]['id']==uid
    assert client.get('/api/me/blocks',headers=other).json()==[]
    assert client.get(f'/api/users/{uid}',headers=owner).status_code==404
    assert client.get(f'/api/users/{own["creator_id"]}',headers=other).status_code==404
    assert [p['id'] for p in client.get('/api/cases',headers=owner).json()]==[own['id']]
    assert client.get(f'/api/cases/{own["id"]}/comments',headers=owner).json()==[]
    assert client.get('/api/me/bookmarks',headers=owner).json()==[]
    assert client.get('/api/notifications',headers=owner).json()['unread_count']==0
    assert client.put(f'/api/cases/{own["id"]}/like',headers=other).status_code==404
    assert client.post(f'/api/cases/{own["id"]}/comments',headers=other,json={'content':'Hello'}).status_code==404
    assert client.put(f'/api/users/{uid}/follow',headers=owner).status_code==404
    assert client.delete(f'/api/users/{uid}/block',headers=other).status_code==200
    assert client.get(f'/api/users/{uid}',headers=owner).status_code==404
    client.delete(f'/api/users/{uid}/block',headers=owner)
    assert client.get(f'/api/users/{uid}',headers=owner).status_code==200
    assert client.get(f'/api/users/{uid}',headers=owner).json()['followers']==0
    assert client.get(f'/api/users/{own["creator_id"]}',headers=other).json()['followers']==0


def test_comment_reports_are_private_and_moderator_can_remove(client):
    owner=account(client,'reportcommentowner');reporter=account(client,'reportcommentuser');moderator=staff_account(client,'reportcommentmod')
    post=create_case(client,owner)
    cid=client.post(f'/api/cases/{post["id"]}/comments',headers=owner,json={'content':'Chợ Bến Thành'}).json()['id']
    assert client.post(f'/api/comments/{cid}/reports',json={'reason':'other'}).status_code==401
    for _ in range(2):assert client.post(f'/api/comments/{cid}/reports',headers=reporter,json={'reason':'privacy','details':'Please review'}).status_code==201
    assert client.get('/api/moderation/queue',headers=reporter).status_code==403
    queue=client.get('/api/moderation/queue',headers=moderator).json()
    assert len(queue['comment_reports'])==1 and queue['comment_reports'][0]['content']=='Chợ Bến Thành'
    assert client.post(f'/api/moderation/comments/{cid}',headers=reporter,json={'action':'remove','reason':'Privacy issue'}).status_code==403
    assert client.post(f'/api/moderation/comments/{cid}',headers=moderator,json={'action':'remove','reason':'Privacy issue'}).status_code==200
    assert client.get('/api/moderation/queue',headers=moderator).json()['comment_reports']==[]
    comments=client.get(f'/api/cases/{post["id"]}/comments',headers=owner).json()
    assert all(c['content']!='Chợ Bến Thành' for c in comments)


def test_recovery_mail_failure_has_generic_response(client,monkeypatch):
    from fastapi import HTTPException
    from app import email_verification
    account(client,'resetdelivery')
    def fail(*args,**kwargs):raise HTTPException(503,'SMTP unavailable')
    monkeypatch.setattr(email_verification,'send_code',fail)
    result=request_recovery(client,'resetdelivery@example.com')
    missing=request_recovery(client,'notregistered@example.com')
    assert result.status_code==missing.status_code==200
    assert result.json()['message']==missing.json()['message']
    assert set(result.json())==set(missing.json())
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(EmailVerification.id).where(EmailVerification.purpose=='password_reset')) is None


def test_community_migration_is_additive_and_repeatable():
    from sqlalchemy import create_engine,text,inspect
    from app.migrations import upgrade
    engine=create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE comments (id INTEGER PRIMARY KEY, case_id INTEGER, user_id INTEGER, content TEXT, is_hidden INTEGER NOT NULL DEFAULT 0, created_at DATETIME)'))
        db.execute(text("INSERT INTO comments (id,case_id,user_id,content) VALUES (1,1,1,'Existing comment')"))
    upgrade(engine);upgrade(engine)
    assert 'is_removed' in {c['name'] for c in inspect(engine).get_columns('comments')}
    assert {'follows','bookmarks','user_blocks','comment_reports'}<=set(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.execute(text('SELECT content,is_removed FROM comments WHERE id=1')).one()==('Existing comment',0)
    engine.dispose()


def test_follow_notifications_group_order_and_refollow_without_duplicates(client):
    owner=account(client,'notifiedowner');first=account(client,'notifiedfirst');second=account(client,'notifiedsecond')
    uid=client.get('/api/me',headers=owner).json()['id']
    first_id=client.get('/api/me',headers=first).json()['id']
    second_id=client.get('/api/me',headers=second).json()['id']
    client.put(f'/api/users/{uid}/follow',headers=first)
    client.put(f'/api/users/{uid}/follow',headers=first)
    first_notice=client.get('/api/notifications',headers=owner).json()
    assert first_notice['unread_count']==1 and len(first_notice['items'])==1
    notice=first_notice['items'][0]
    assert notice['kind']=='follow' and notice['case_id'] is None and notice['case_title'] is None
    assert notice['target_user_id']==first_id
    assert client.post(f'/api/notifications/{notice["id"]}/read',headers=first).status_code==404
    client.post(f'/api/notifications/{notice["id"]}/read',headers=owner)
    client.delete(f'/api/users/{uid}/follow',headers=first)
    client.put(f'/api/users/{uid}/follow',headers=first)
    assert client.get('/api/notifications',headers=owner).json()['unread_count']==0
    client.put(f'/api/users/{uid}/follow',headers=second)
    grouped=client.get('/api/notifications',headers=owner).json()
    assert grouped['unread_count']==1 and len(grouped['items'])==1
    latest=grouped['items'][0]
    assert latest['actor_count']==2 and latest['target_user_id']==second_id
    assert [p['id'] for p in latest['actors']]==[second_id,first_id]
    client.post(f'/api/notifications/{notice["id"]}/read',headers=owner)
    assert client.get('/api/notifications',headers=owner).json()['unread_count']==1
    client.put(f'/api/users/{second_id}/block',headers=owner)
    assert client.get('/api/notifications',headers=owner).json()['unread_count']==0
    assert client.get('/api/notifications',headers=owner).json()['items'][0]['actor_count']==1
    assert client.put(f'/api/users/{uid}/follow',headers=second).status_code==404


def test_notification_migration_preserves_history_and_supports_follows():
    from sqlalchemy import create_engine,text,inspect,event
    from sqlalchemy.orm import Session
    from app.database import Base
    from app.models import Notification
    from app.migrations import upgrade
    engine=create_engine('sqlite://')
    @event.listens_for(engine,'connect')
    def fk_on(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner=User(username='oldowner',password_hash='test');actor=User(username='oldactor',password_hash='test')
        db.add_all([owner,actor]);db.flush()
        post=Case(creator_id=owner.id,title='Preserved',image_url='/uploads/example.jpg',answer='Private')
        db.add(post);db.commit();owner_id=owner.id;actor_id=actor.id;case_id=post.id
    with engine.begin() as db:
        db.execute(text('DROP TABLE notifications'))
        db.execute(text('CREATE TABLE notifications (event_key VARCHAR(100) NOT NULL UNIQUE, id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES users(id), actor_id INTEGER NOT NULL REFERENCES users(id), case_id INTEGER NOT NULL REFERENCES cases(id), kind VARCHAR(20) NOT NULL, is_read INTEGER NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'))
        db.execute(text('CREATE INDEX ix_notifications_recipient_id ON notifications (recipient_id)'))
        db.execute(text("INSERT INTO notifications (id,event_key,recipient_id,actor_id,case_id,kind,is_read) VALUES (17,'old-event',:owner,:actor,:post,'like',1)"),{'owner':owner_id,'actor':actor_id,'post':case_id})
    upgrade(engine);upgrade(engine)
    assert next(c for c in inspect(engine).get_columns('notifications') if c['name']=='case_id')['nullable']
    with Session(engine) as db:
        previous=db.get(Notification,17)
        assert previous.event_key=='old-event' and previous.is_read==1 and previous.case_id==case_id
        notice=Notification(event_key='new-follow',recipient_id=owner_id,actor_id=actor_id,kind='follow')
        db.add(notice);db.commit()
        assert notice.id>17 and notice.case_id is None
    engine.dispose()


def test_change_password_requires_current_password_and_revokes_old_sessions(client):
    owner=account(client,'changepassword')
    request=request_recovery(client,'changepassword@example.com').json();code=client.email_codes[-1][1]
    assert client.post('/api/me/password',json={'current_password':'test-password-123','new_password':'next-password-123'}).status_code==401
    assert client.post('/api/me/password',headers=owner,json={'current_password':'wrong-password-123','new_password':'next-password-123'}).status_code==400
    assert client.get('/api/me',headers=owner).status_code==200
    assert client.post('/api/me/password',headers=owner,json={'current_password':'test-password-123','new_password':'test-password-123'}).status_code==400
    changed=client.post('/api/me/password',headers=owner,json={'current_password':'test-password-123','new_password':'next-password-123'})
    assert changed.status_code==200
    assert client.get('/api/me',headers=owner).status_code==401
    assert client.post('/api/auth/password-reset/confirm',json={'challenge_id':request['challenge_id'],'code':code,'new_password':'stale-code-password'}).status_code==400
    assert client.post('/api/auth/login',json={'username':'changepassword','password':'test-password-123'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'changepassword','password':'next-password-123'}).status_code==200
    staff=staff_account(client,'changestaff')
    assert client.post('/api/me/password',headers=staff,json={'current_password':'test-password-123','new_password':'next-password-123'}).status_code==403


def test_device_sessions_are_private_revocable_and_keep_history(client):
    owner=account(client,'deviceowner');other=account(client,'deviceother')
    login=client.post('/api/auth/login',json={'username':'deviceowner','password':'test-password-123'},headers={'user-agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17 Mobile Safari/604.1','X-Forwarded-For':'8.8.8.8'})
    second={'Authorization':'Bearer '+login.json()['token']}
    listing=client.get('/api/me/sessions',headers=owner)
    assert listing.status_code==200 and listing.headers['cache-control']=='no-store'
    rows=listing.json()['items']
    assert len(rows)==2 and sum(r['is_current'] for r in rows)==1
    safari=next(r for r in rows if 'iPhone' in r['device'])
    assert 'Safari' in safari['device'] and safari['active'] and not safari['is_current']
    assert safari['login_at'] and safari['ip_address'] is None
    assert not any('token_hash' in r or 'user_agent' in r for r in rows)
    assert login.json()['token'] not in listing.text
    assert client.delete(f'/api/me/sessions/{safari["id"]}',headers=other).status_code==404
    assert client.get('/api/me/sessions').status_code==401
    assert client.delete(f'/api/me/sessions/{safari["id"]}',headers=owner).status_code==200
    assert client.get('/api/me',headers=second).status_code==401
    history=client.get('/api/me/sessions',headers=owner).json()['items']
    assert next(r for r in history if r['id']==safari['id'])['active'] is False
    third=client.post('/api/auth/login',json={'username':'deviceowner','password':'test-password-123'}).json()['token']
    assert client.post('/api/me/sessions/revoke-others',headers=owner).status_code==200
    assert client.get('/api/me',headers={'Authorization':'Bearer '+third}).status_code==401
    assert client.get('/api/me',headers=owner).status_code==200
    current=next(r for r in client.get('/api/me/sessions',headers=owner).json()['items'] if r['is_current'])
    assert client.delete(f'/api/me/sessions/{current["id"]}',headers=owner).status_code==200
    assert client.get('/api/me',headers=owner).status_code==401


def test_legacy_session_is_observed_without_faking_login_date(client):
    import hashlib,time
    from app.models import Token
    owner=account(client,'legacydevice');uid=client.get('/api/me',headers=owner).json()['id']
    raw='legacy-session-for-test'
    with next(app.dependency_overrides[get_db]()) as db:
        db.add(Token(token_hash=hashlib.sha256(raw.encode()).hexdigest(),user_id=uid,expires_at=time.time()+3600));db.commit()
    headers={'Authorization':'Bearer '+raw,'User-Agent':'Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0'}
    result=client.get('/api/me/sessions',headers=headers).json()['items']
    current=next(r for r in result if r['is_current'])
    assert current['login_at'] is None and current['last_seen_at']
    assert current['device']=='Chrome · Windows'
    assert client.get('/api/me/sessions?offset=-1',headers=headers).status_code==400


def test_device_ip_uses_asgi_address_not_forwarded_header():
    from types import SimpleNamespace
    from app.login_sessions import client_ip,device_name
    request=SimpleNamespace(client=SimpleNamespace(host='8.8.8.8'),headers={'X-Forwarded-For':'1.2.3.4'})
    assert client_ip(request)=='8.8.8.8'
    assert client_ip(SimpleNamespace(client=SimpleNamespace(host='not-an-ip'))) is None
    assert device_name('Mozilla/5.0 (Windows NT 10.0) Edg/120')=='Edge · Windows'


def test_xp_is_private_but_leaderboard_still_sorts_by_it(client):
    first=account(client,'privatepointsfirst');second=account(client,'privatepointssecond')
    first_id=client.get('/api/me',headers=first).json()['id']
    second_id=client.get('/api/me',headers=second).json()['id']
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(User,first_id).total_xp=1234;db.get(User,second_id).total_xp=5678;db.commit()
    hidden={'xp','xp_in_level','xp_for_next_level','xp_to_next_level','total_xp'}
    board=client.get('/api/leaderboard').json()
    assert [p['id'] for p in board]==[second_id,first_id]
    assert all(not hidden.intersection(p) for p in board)
    assert all('level' in p and 'avatar_frame' in p for p in board)
    assert not hidden.intersection(client.get(f'/api/users/{first_id}',headers=second).json())
    client.put(f'/api/users/{first_id}/follow',headers=second)
    follower=client.get(f'/api/users/{first_id}/followers').json()[0]
    assert not hidden.intersection(follower)
    actor=client.get('/api/notifications',headers=first).json()['items'][0]['actor']
    assert not hidden.intersection(actor)
    private=client.get('/api/me',headers=first).json()
    assert private['xp']==1234 and 'xp_in_level' in private and 'xp_to_next_level' in private
