import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.legal import VERSION

def staff_account(client,username,role='moderator'):
    from app.models import User
    headers=account(client,username)
    with next(app.dependency_overrides[get_db]()) as db:
        user=db.scalar(select(User).where(User.username==username));user.role=role;db.commit()
    return headers

def test_moderation_private_queue_redaction_reports_and_suspension(client,monkeypatch):
    from app.models import ModerationAudit
    monkeypatch.setenv('MODERATION_REQUIRE_REVIEW','1')
    owner=account(client,'reviewowner');other=account(client,'reviewother')
    moderator=staff_account(client,'reviewmod');admin=staff_account(client,'reviewadmin','admin')
    image=io.BytesIO();Image.new('RGB',(100,80),'red').save(image,'PNG')
    uploaded=client.post('/api/uploads',headers=owner,files={'file':('test.png',image.getvalue(),'image/png')},data={'rights_confirmed':'true'}).json()
    url=uploaded['image_url']
    assert uploaded['moderation_status']=='pending'
    assert uploaded['scan']['state']=='unavailable'
    assert client.get(url).status_code==404
    assert client.get(url,headers=other).status_code==404
    assert client.get(url,headers=owner).status_code==200
    assert client.get(url,headers=moderator).status_code==200
    created=client.post('/api/cases',headers=owner,json={'title':'Review me','answer':'secret place','image_url':url,'content_rights_confirmed':True}).json()
    case_id=created['id']
    assert created['moderation_status']=='pending'
    assert client.get('/api/cases').json()==[]
    assert client.get(f'/api/cases/{case_id}').status_code==404
    assert client.get('/api/moderation/queue',headers=other).status_code==403
    assert client.post(f'/api/moderation/cases/{case_id}',headers=moderator,json={'action':'approve','reason':'Checked content'}).status_code==409
    redacted=client.post('/api/moderation/images/redact',headers=moderator,json={'image_url':url,'boxes':[[.1,.1,.4,.4]],'reason':'Hide private detail'})
    assert redacted.status_code==200,redacted.text
    new_url=redacted.json()['image_url'];assert new_url!=url
    assert client.get(url).status_code==404
    assert client.post('/api/moderation/images/decision',headers=moderator,json={'image_url':url,'action':'approve','reason':'Stale original request'}).status_code==409
    assert client.post('/api/moderation/images/decision',headers=moderator,json={'image_url':new_url,'action':'approve','reason':'Checked redaction'}).status_code==200
    assert client.post(f'/api/moderation/cases/{case_id}',headers=moderator,json={'action':'approve','reason':'Checked content'}).status_code==200
    assert client.get(new_url).status_code==200
    assert client.get(f'/api/cases/{case_id}').status_code==200
    report=client.post(f'/api/cases/{case_id}/reports',headers=other,json={'reason':'privacy','details':'Please check the image'})
    assert report.status_code==201
    assert len(client.get('/api/moderation/queue',headers=moderator).json()['reports'])==1
    owner_id=created['creator_id']
    assert client.post(f'/api/moderation/users/{owner_id}/suspension',headers=moderator,json={'suspended':True,'reason':'Repeated violations'}).status_code==200
    assert client.get('/api/me',headers=owner).status_code==401
    assert client.get(new_url).status_code==404
    assert client.get('/api/cases').json()==[]
    assert client.post(f'/api/moderation/users/{owner_id}/suspension',headers=moderator,json={'suspended':False,'reason':'Appeal reviewed'}).status_code==403
    assert client.post(f'/api/moderation/users/{owner_id}/suspension',headers=admin,json={'suspended':False,'reason':'Appeal reviewed'}).status_code==200
    assert client.post(f'/api/moderation/cases/{case_id}',headers=moderator,json={'action':'remove','reason':'Privacy violation'}).status_code==200
    assert client.get(new_url).status_code==404
    assert client.get(f'/api/cases/{case_id}/comments').status_code==404
    assert client.post(f'/api/cases/{case_id}/like',headers=other).status_code in (404,405)
    with next(app.dependency_overrides[get_db]()) as db:
        assert len(list(db.scalars(select(ModerationAudit))))>=6

def test_scanner_failure_faces_and_sensitive_detection(tmp_path,monkeypatch):
    from app import image_safety
    monkeypatch.setenv('IMAGE_SCANNER','nudenet')
    image=tmp_path/'sample.jpg'
    Image.effect_noise((100,100),100).convert('RGB').save(image)
    before=image.read_bytes()
    class FakeDetector:
        def detect(self,path):
            return [{'class':'FACE_MALE','score':.9,'box':[10,10,40,40]},{'class':'MALE_GENITALIA_EXPOSED','score':.9,'box':[60,60,20,20]}]
    monkeypatch.setattr(image_safety,'detector',lambda:FakeDetector())
    result=image_safety.scan_image(image)
    assert result['state']=='scanned' and result['faces_blurred']==1 and result['sensitive']
    assert image.read_bytes()!=before
    def unavailable(): raise RuntimeError('model unavailable')
    monkeypatch.setattr(image_safety,'detector',unavailable)
    assert image_safety.scan_image(image)['state']=='error'

def test_avatar_pending_not_public_until_approved(client,monkeypatch):
    monkeypatch.setenv('MODERATION_REQUIRE_REVIEW','1')
    owner=account(client,'avatarpending');moderator=staff_account(client,'avatarmod')
    image=io.BytesIO();Image.new('RGB',(80,80),'blue').save(image,'PNG')
    result=client.post('/api/me/avatar',headers=owner,files={'file':('avatar.png',image.getvalue(),'image/png')},data={'rights_confirmed':'true'}).json()
    assert result['avatar_url'] is None and result['moderation_status']=='pending'
    row=client.get('/api/moderation/queue',headers=moderator).json()['images'][0]
    assert client.get(row['image_url']).status_code==404
    client.post('/api/moderation/images/decision',headers=moderator,json={'image_url':row['image_url'],'action':'approve','reason':'Avatar checked'})
    assert client.get('/api/me',headers=owner).json()['avatar_url']==row['image_url']
    assert client.get(row['image_url']).status_code==200

def test_failed_scan_cannot_auto_publish_and_role_not_self_assigned(client,monkeypatch):
    from app import main
    monkeypatch.setattr(main,'scan_image',lambda path:{'state':'error','warnings':['model failed']})
    response=client.post('/api/auth/register',json={'username':'notstaff','password':'test-password-123','email':'notstaff@example.com','role':'admin',**LEGAL_FIELDS})
    assert response.status_code==422
    headers=account(client,'notstaff')
    assert client.get('/api/me',headers=headers).json()['role']=='user'
    assert client.get('/api/moderation/queue',headers=headers).status_code==403
    image=io.BytesIO();Image.new('RGB',(80,80),'blue').save(image,'PNG')
    result=client.post('/api/uploads',headers=headers,files={'file':('a.png',image.getvalue(),'image/png')},data={'rights_confirmed':'true'}).json()
    assert result['moderation_status']=='pending'
    assert client.get(result['image_url']).status_code==404

@pytest.mark.parametrize('scan,expected',[
    ({'state':'scanned','sensitive':False,'faces_blurred':0},'approved'),
    ({'state':'scanned','sensitive':False,'faces_blurred':2},'approved'),
    ({'state':'scanned','sensitive':True,'faces_blurred':1},'pending'),
    ({'state':'error','sensitive':False},'pending'),
    ({'state':'unavailable','sensitive':False},'pending'),
    ({'state':'scanned'},'pending'),
])
def test_automatic_review_only_after_successful_clean_scan(client,monkeypatch,scan,expected):
    from app import main
    monkeypatch.setenv('MODERATION_REQUIRE_REVIEW','1')
    monkeypatch.setenv('AUTO_APPROVE_SCANNED','1')
    monkeypatch.setattr(main,'scan_image',lambda path:dict(scan))
    owner=account(client,'autouser')
    image=io.BytesIO();Image.new('RGB',(80,80),'blue').save(image,'PNG')
    result=client.post('/api/uploads',headers=owner,files={'file':('a.png',image.getvalue(),'image/png')},data={'rights_confirmed':'true'}).json()
    assert result['moderation_status']==expected
    posted=client.post('/api/cases',headers=owner,json={'title':'Automatic review','answer':'secret place','image_url':result['image_url'],'content_rights_confirmed':True})
    assert posted.status_code==201
    assert posted.json()['moderation_status']==('published' if expected=='approved' else 'pending')
    assert client.get(result['image_url']).status_code==(200 if expected=='approved' else 404)

LEGAL_FIELDS = {'player_birth_date':'2000-01-01','terms_accepted':True,'privacy_accepted':True,'legal_version':VERSION}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MODERATION_REQUIRE_REVIEW","0")
    monkeypatch.setenv("IMAGE_SCANNER","off")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def database():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()

def account(client, username):
    r = client.post('/api/auth/register', json={'username': username, 'password': 'test-password-123', 'email': f'{username}@example.com',**LEGAL_FIELDS})
    assert r.status_code == 201, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}

def create_case(client, headers, **extra):
    stream = io.BytesIO()
    image = Image.new('RGB', (64, 48), 'green')
    exif = Image.Exif()
    exif[270] = 'Private original metadata'
    image.save(stream, 'JPEG', exif=exif)
    r = client.post('/api/uploads', headers=headers, data={'rights_confirmed':'true'},files={'file': ('secret-location.jpg', stream.getvalue(), 'image/jpeg')})
    assert r.status_code == 201
    url = r.json()['image_url']
    clean = Image.open(io.BytesIO(client.get(url,headers=headers).content))
    assert not clean.getexif()
    body = dict(title='Góc phố bí ẩn', answer='Chợ Bến Thành', image_url=url, content_rights_confirmed=True,**extra)
    r = client.post('/api/cases', headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()

def test_game_privacy_scoring_and_comments(client):
    owner = account(client, 'owner')
    player = account(client, 'player')
    case = create_case(client, owner, latitude=10.772, longitude=106.698)
    for endpoint in ['/api/cases', f'/api/cases/{case["id"]}']:
        payload = client.get(endpoint).text
        assert 'Chợ Bến Thành' not in payload
        assert '10.772' not in payload
        assert '106.698' not in payload
    path = f'/api/cases/{case["id"]}'
    assert client.post(path + '/guesses', json={'answer': 'Chợ Bến Thành'}).status_code == 401
    assert client.post(path + '/guesses', headers=owner, json={'answer': 'Chợ Bến Thành'}).status_code == 400
    assert client.post(path + '/guesses', headers=player, json={'answer': 'Hà Nội'}).json()['status'] == 'incorrect'
    assert client.post(path + '/guesses', headers=player, json={'answer': 'CHO BEN THANH!'}).json()['reward_xp'] == 50
    assert client.post(path + '/guesses', headers=player, json={'answer': 'Chợ Bến Thành'}).json()['reward_xp'] == 0
    assert client.get('/api/me', headers=player).json()['xp'] == 50
    r = client.post(path + '/comments', headers=player, json={'content': 'Đây là Chợ Bến Thành nè!'})
    assert r.json()['is_hidden'] is True
    client.post(path + '/comments', headers=player, json={'content': 'Ảnh đẹp quá!'})
    comments = client.get(path + '/comments').json()
    assert comments[0]['content'] == 'Ảnh đẹp quá!'
    assert 'Chợ Bến Thành' not in str(comments)
    assert client.get('/api/leaderboard').json()[0]['username'] == 'player'

def test_coordinates_rate_limit_and_validation(client):
    owner, player = account(client, 'owner'), account(client, 'player')
    c = create_case(client, owner, latitude=10.772, longitude=106.698)
    path = f'/api/cases/{c["id"]}/guesses'
    assert client.post(path, headers=player, json={'latitude': 100, 'longitude': 1}).status_code == 422
    assert client.post(path, headers=player, json={'latitude': 10.772, 'longitude': 106.698}).json()['status'] == 'correct'
    other = account(client, 'other')
    for _ in range(10):
        assert client.post(path, headers=other, json={'answer': 'wrong'}).status_code == 200
    assert client.post(path, headers=other, json={'answer': 'wrong'}).status_code == 429
    assert client.get('/api/cases?offset=-1').status_code == 422
    assert client.post('/api/uploads', headers=owner, files={'file': ('x.jpg', b'not an image', 'image/jpeg')}).status_code == 400

def test_auth_logout_and_upload_ownership(client):
    owner, player = account(client, 'owner'), account(client, 'player')
    assert client.post('/api/auth/register', json={'username': 'OWNER', 'password': 'test-password-123', 'email': 'another@example.com',**LEGAL_FIELDS}).status_code == 409
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'test-password-123'}).status_code == 200
    c = create_case(client, owner)
    assert client.post('/api/cases', headers=player, json={'title': 'Another', 'answer': 'Somewhere', 'image_url': c['image_url'],'content_rights_confirmed':True}).status_code == 400
    assert client.post('/api/auth/logout', headers=player).status_code == 204
    assert client.get('/api/me', headers=player).status_code == 401
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200

def test_contact_registration_profile_and_privacy(client):
    base = {'username': 'tester', 'password': 'test-password-123',**LEGAL_FIELDS}
    assert client.post('/api/auth/register', json=base).status_code == 422
    assert client.post('/api/auth/register', json={**base, 'email': 'bad@'}).status_code == 422
    assert client.post('/api/auth/register', json={**base, 'phone': 'abc'}).status_code == 422
    r = client.post('/api/auth/register', json={**base, 'phone': '090 123 4567', 'display_name': ' Người khám phá '})
    assert r.status_code == 201
    headers = {'Authorization': 'Bearer ' + r.json()['token']}
    assert r.json()['user']['phone'] == '+84901234567'
    assert r.json()['user']['display_name'] == 'Người khám phá'
    for identifier in ['0901234567', '+84901234567', 'tester']:
        assert client.post('/api/auth/login', json={'username': identifier, 'password': base['password']}).status_code == 200
    assert client.patch('/api/me', json={'bio': 'hi'}).status_code == 401
    assert client.patch('/api/me', headers=headers, json={'phone': ''}).status_code == 400
    assert client.patch('/api/me', headers=headers, json={'xp': 9000}).status_code == 422
    result = client.patch('/api/me', headers=headers, json={'email': ' TESTER@EXAMPLE.COM ', 'bio': ' Thích khám phá ', 'phone': None})
    assert result.status_code == 200
    assert result.json()['email'] == 'tester@example.com'
    assert result.json()['bio'] == 'Thích khám phá'
    assert result.json()['phone'] is None
    assert result.json()['contact_verified'] is False
    assert client.post('/api/auth/login', json={'username': 'TESTER@example.com', 'password': base['password']}).status_code == 200
    other = account(client, 'other')
    assert client.patch('/api/me', headers=other, json={'email': 'tester@example.com'}).status_code == 409
    assert client.get('/api/me', headers=other).json()['email'] == 'other@example.com'
    assert client.post('/api/auth/register', json={**base, 'username': 'newuser', 'email': 'Tester@example.com'}).status_code == 409
    board = client.get('/api/leaderboard').json()
    assert all('email' not in u and 'phone' not in u and 'contact_verified' not in u for u in board)

def test_upgrade_preserves_legacy_data(tmp_path):
    from sqlalchemy import text, inspect
    from app.migrations import upgrade
    from app.models import User
    from app.main import password_hash
    from sqlalchemy.orm import Session
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, total_xp INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO users VALUES (1, :name, :password, 250)'), {'name': 'legacy', 'password': password_hash('legacy-password')})
    upgrade(engine)
    upgrade(engine)
    with Session(engine) as db:
        user = db.get(User, 1)
        assert user.username == 'legacy' and user.total_xp == 250
        assert user.email is None and user.phone is None
        assert user.avatar_url is None
    assert 'external_identities' in inspect(engine).get_table_names()
    assert {'likes','notifications','answer_aliases'} <= set(inspect(engine).get_table_names())
    engine.dispose()

def test_avatar_upload_display_name_and_comment_identity(client):
    owner, player = account(client, 'owner'), account(client, 'player')
    case = create_case(client, owner)
    image = Image.new('RGB', (900, 450), 'blue')
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[270] = 'Private image metadata'
    image.save(stream, 'JPEG', exif=exif)
    files = {'file': ('my-location.jpg', stream.getvalue(), 'image/jpeg')}
    assert client.post('/api/me/avatar', files=files).status_code == 401
    assert client.delete('/api/me/avatar').status_code == 401
    assert client.post('/api/me/avatar', headers=player, files={'file': ('bad.jpg', b'bad', 'image/jpeg')}).status_code == 400
    uploaded = client.post('/api/me/avatar', headers=player, data={'rights_confirmed':'true'},files=files)
    assert uploaded.status_code == 200
    avatar_url = uploaded.json()['avatar_url']
    assert avatar_url.startswith('/uploads/avatar-')
    clean = Image.open(io.BytesIO(client.get(avatar_url).content))
    assert clean.size == (512, 512) and not clean.getexif()
    assert client.get('/api/me', headers=owner).json()['avatar_url'] is None
    assert client.patch('/api/me', headers=player, json={'avatar_url':'https://example.com/track.jpg'}).status_code == 422
    assert client.post('/api/cases', headers=player, json={'title':'Somewhere', 'answer':'A place', 'image_url':avatar_url,'content_rights_confirmed':True}).status_code == 400
    client.patch('/api/me', headers=player, json={'display_name':'Người thích khám phá'})
    path = f'/api/cases/{case["id"]}/comments'
    client.post(path, headers=player, json={'content':'Góc ảnh đẹp!'})
    comment = client.get(path).json()[0]
    assert comment['display_name'] == 'Người thích khám phá'
    assert comment['avatar_url'] == avatar_url
    assert 'email' not in comment and 'phone' not in comment
    client.patch('/api/me', headers=player, json={'display_name':''})
    assert client.get(path).json()[0]['display_name'] == 'player'
    client.patch('/api/me', headers=owner, json={'display_name':'Chủ thử thách'})
    public_case = client.get(f'/api/cases/{case["id"]}').json()
    assert public_case['creator_display_name'] == 'Chủ thử thách'
    assert public_case['creator'] == 'owner'
    assert 'email' not in public_case and 'phone' not in public_case
    assert client.delete('/api/me/avatar', headers=player).json()['avatar_url'] is None
    assert client.get(path).json()[0]['avatar_url'] is None

def test_likes_and_private_notifications(client):
    owner, player, other = account(client, 'owner'), account(client, 'player'), account(client, 'other')
    case = create_case(client, owner)
    path = f'/api/cases/{case["id"]}'
    assert client.put(path+'/like').status_code == 401
    assert client.get('/api/notifications').status_code == 401
    for _ in range(2):
        assert client.put(path+'/like', headers=player).json() == {'likes':1,'liked_by_me':True}
    assert client.get(path, headers=player).json()['liked_by_me'] is True
    assert client.get(path).json()['liked_by_me'] is False
    inbox = client.get('/api/notifications', headers=owner).json()
    assert inbox['unread_count'] == 1 and len(inbox['items']) == 1
    entry = inbox['items'][0]
    assert entry['kind'] == 'like' and 'email' not in entry['actor'] and 'phone' not in entry['actor']
    assert client.post(f'/api/notifications/{entry["id"]}/read', headers=other).status_code == 404
    assert client.post(f'/api/notifications/{entry["id"]}/read', headers=owner).status_code == 200
    assert client.delete(path+'/like', headers=player).json()['likes'] == 0
    client.put(path+'/like', headers=player)
    assert client.get('/api/notifications', headers=owner).json()['unread_count'] == 0
    client.put(path+'/like', headers=owner)
    assert client.get('/api/notifications', headers=owner).json()['unread_count'] == 0
    assert client.get('/api/me', headers=player).json()['xp'] == 0
    client.post(path+'/comments', headers=other, json={'content':'Một góc ảnh đẹp!'})
    client.post('/api/notifications/read', headers=owner, json={'through_id':entry['id']})
    assert client.get('/api/notifications', headers=owner).json()['unread_count'] == 1
    latest = client.get('/api/notifications', headers=owner).json()['items'][0]
    assert latest['kind'] == 'comment' and 'content' not in latest
    client.post('/api/notifications/read', headers=owner, json={'through_id':latest['id']})
    assert client.get('/api/notifications', headers=owner).json()['unread_count'] == 0

def test_combined_comment_guesses_aliases_and_hidden_answers(client):
    owner, player, other = account(client, 'owner'), account(client, 'player'), account(client, 'other')
    c = create_case(client, owner, aliases=['Ben Thanh Market'])
    path = f'/api/cases/{c["id"]}/comments'
    public = client.get(f'/api/cases/{c["id"]}').json()
    assert 'aliases' not in public and 'answer' not in public
    for text in ['Bến Thành', 'Cho Ben Thanhmarket', 'Một góc phố đẹp']:
        result = client.post(path, headers=player, json={'content':text}).json()
        assert result['is_hidden'] is False and result['reward_xp'] == 0
    negative = client.post(path, headers=player, json={'content':'Không phải Chợ Bến Thành đâu'}).json()
    assert negative['is_hidden'] is True and negative['reward_xp'] == 0
    correct = client.post(path, headers=player, json={'content':'Mình nghĩ đây là BEN THANH MARKET!'}).json()
    assert correct['status'] == 'correct' and correct['reward_xp'] == 50 and correct['is_hidden'] is True
    again = client.post(path, headers=player, json={'content':'Đây là Chợ Bến Thành'}).json()
    assert again['status'] == 'already_solved' and again['reward_xp'] == 0
    assert client.get('/api/me', headers=player).json()['xp'] == 50
    own = client.post(path, headers=owner, json={'content':'Chợ Bến Thành'}).json()
    assert own['status'] == 'author' and own['reward_xp'] == 0
    comments = client.get(path).json()
    assert all('chợ bến thành' not in row['content'].lower() and 'ben thanh market' not in row['content'].lower() for row in comments)
    assert any(n['kind']=='solve' for n in client.get('/api/notifications', headers=owner).json()['items'])
    assert client.post(f'/api/cases/{c["id"]}/guesses', headers=other, json={'answer':'Ben Thanh Market'}).json()['reward_xp'] == 50

def test_combined_comment_gps_and_rate_limit(client):
    owner, player, other = account(client, 'owner'), account(client, 'player'), account(client, 'other')
    c = create_case(client, owner, latitude=10.772, longitude=106.698)
    path = f'/api/cases/{c["id"]}/comments'
    assert client.post(path, headers=player, json={'content':''}).status_code == 422
    assert client.post(path, headers=player, json={'latitude':10.772}).status_code == 422
    result = client.post(path, headers=player, json={'latitude':10.772,'longitude':106.698}).json()
    assert result['status']=='correct' and result['is_hidden'] and result['reward_xp']==50
    assert '10.772' not in client.get(path).text and '106.698' not in client.get(path).text
    for i in range(10):
        assert client.post(path, headers=other, json={'content':f'Bình luận {i}'}).status_code == 201
    assert client.post(path, headers=other, json={'content':'Chợ Bến Thành'}).status_code == 429
    assert client.get('/api/me', headers=other).json()['xp']==0

def test_notification_pagination(client):
    from app.models import Notification
    owner, player = account(client, 'owner'), account(client, 'player')
    c = create_case(client, owner)
    owner_id = client.get('/api/me', headers=owner).json()['id']
    actor_id = client.get('/api/me', headers=player).json()['id']
    database = app.dependency_overrides[get_db]()
    db = next(database)
    for i in range(35):
        db.add(Notification(recipient_id=owner_id, actor_id=actor_id, case_id=c['id'], kind='comment',event_key=f'qa-comment:{i}'))
    db.commit()
    database.close()
    page = client.get('/api/notifications', headers=owner).json()
    assert len(page['items'])==30 and page['unread_count']==35
    older = client.get(f'/api/notifications?before_id={page["next_before_id"]}', headers=owner).json()
    assert len(older['items'])==5 and older['next_before_id'] is None
    assert not ({n['id'] for n in page['items']} & {n['id'] for n in older['items']})
    assert client.get('/api/notifications', headers=player).json()['items']==[]

def test_explicit_legal_consent_and_rights(client):
    from app.models import LegalConsent, ContentAttestation
    base={'username':'legaluser','email':'legal@example.com','password':'test-password-123',**LEGAL_FIELDS}
    for change in [{'terms_accepted':False},{'privacy_accepted':False},{'privacy_accepted':'true'},{'legal_version':'old'},{'player_birth_date':'2100-01-01'}]:
        assert client.post('/api/auth/register',json={**base,**change}).status_code==422
    missing=base.copy();missing.pop('terms_accepted')
    assert client.post('/api/auth/register',json=missing).status_code==422
    response=client.post('/api/auth/register',json=base)
    assert response.status_code==201
    headers={'Authorization':'Bearer '+response.json()['token']}
    assert client.get('/api/me',headers=headers).json()['needs_legal_consent'] is False
    assert client.post('/api/uploads',headers=headers,files={'file':('x.jpg',b'bad','image/jpeg')}).status_code==400
    c=create_case(client,headers)
    assert client.post('/api/cases',headers=headers,json={'title':'New case','answer':'A place','image_url':c['image_url']}).status_code==422
    database=app.dependency_overrides[get_db]();db=next(database)
    consent=db.scalar(select(LegalConsent))
    import json
    snapshot=json.loads(consent.notice_snapshot)
    assert consent.version==VERSION and consent.actor_type=='adult' and consent.accepted_at>0
    assert all(len(digest)==64 for digest in snapshot['documents'].values())
    assert len(list(db.scalars(select(ContentAttestation))))==2
    database.close()

def test_guardian_activation_no_token_leak_and_controls(client,monkeypatch):
    import app.legal as legal
    sent=[]
    monkeypatch.setattr(legal,'send_guardian_email',lambda email,link:sent.append((email,link)))
    data={'username':'youngplayer','password':'old-password-123',**LEGAL_FIELDS,'player_birth_date':'2013-05-17','guardian_email':'parent@example.com'}
    response=client.post('/api/auth/register',json=data)
    assert response.status_code==201 and response.json()['status']=='pending_guardian'
    assert 'token' not in response.json() and 'link' not in response.json()
    assert client.post('/api/auth/login',json={'username':'youngplayer','password':'old-password-123'}).status_code==403
    assert 'youngplayer' not in client.get('/api/leaderboard').text
    from urllib.parse import urlsplit,parse_qs
    raw=parse_qs(urlsplit(sent[0][1]).fragment)['token'][0]
    assert '?' not in sent[0][1] and len(raw)>=32
    preview=client.post('/api/guardian/preview',json={'token':raw}).json()
    assert preview['requires_child_assent'] is True
    assert 'player_birth_date' not in preview and 'guardian_email' not in preview
    approval={'token':raw,'legal_version':VERSION,'terms_accepted':True,'privacy_accepted':True,'guardian_name':'Người đại diện','guardian_birth_date':'1985-01-01','relationship':'mother','authority_confirmed':True,'child_assent_confirmed':True,'new_password':'parent-password-123','display_name':'Nhà khám phá nhỏ'}
    assert client.post('/api/guardian/approve',json={**approval,'child_assent_confirmed':False}).status_code==400
    assert client.post('/api/guardian/approve',json={**approval,'guardian_birth_date':'2015-01-01'}).status_code==422
    assert client.post('/api/guardian/approve',json=approval).status_code==200
    assert client.post('/api/guardian/approve',json=approval).status_code==400
    assert client.post('/api/guardian/preview',json={'token':raw}).status_code==400
    assert client.post('/api/auth/login',json={'username':'youngplayer','password':'old-password-123'}).status_code==401
    login=client.post('/api/auth/login',json={'username':'parent@example.com','password':'parent-password-123'})
    assert login.status_code==200
    headers={'Authorization':'Bearer '+login.json()['token']}
    assert login.json()['user']['guardian_managed'] is True
    assert login.json()['user']['needs_legal_consent'] is False
    owner=account(client,'owner');c=create_case(client,owner,latitude=10.772,longitude=106.698)
    assert client.post(f'/api/cases/{c["id"]}/comments',headers=headers,json={'latitude':10.772,'longitude':106.698}).status_code==403
    assert client.post(f'/api/cases/{c["id"]}/comments',headers=headers,json={'content':'Ảnh đẹp quá'}).status_code==201
    public=client.get('/api/leaderboard').text
    assert 'parent@example.com' not in public and '1985-01-01' not in public and '2013-05-17' not in public

def test_guardian_mail_failure_and_expiry(client,monkeypatch):
    import app.legal as legal
    from app.models import User,GuardianInvite
    monkeypatch.delenv('SMTP_HOST',raising=False);monkeypatch.delenv('SMTP_FROM',raising=False)
    data={'username':'pendingchild',**LEGAL_FIELDS,'player_birth_date':'2022-01-01','guardian_email':'parent@example.com'}
    assert client.post('/api/auth/register',json=data).status_code==503
    database=app.dependency_overrides[get_db]();db=next(database)
    assert db.scalar(select(User).where(User.username=='pendingchild')) is None
    database.close()
    sent=[];monkeypatch.setattr(legal,'send_guardian_email',lambda email,link:sent.append(link))
    assert client.post('/api/auth/register',json=data).status_code==201
    raw=sent[0].split('#token=')[1]
    assert client.post('/api/guardian/preview',json={'token':raw}).json()['requires_child_assent'] is False
    database=app.dependency_overrides[get_db]();db=next(database)
    db.scalar(select(GuardianInvite)).expires_at=0;db.commit();database.close()
    assert client.post('/api/guardian/preview',json={'token':raw}).status_code==400

def test_legacy_consent_and_withdrawal_revokes_sessions(client):
    from app.models import LegalConsent
    headers=account(client,'legacy')
    user_id=client.get('/api/me',headers=headers).json()['id']
    database=app.dependency_overrides[get_db]();db=next(database)
    from sqlalchemy import delete
    db.execute(delete(LegalConsent).where(LegalConsent.user_id==user_id));db.commit();database.close()
    assert client.get('/api/me',headers=headers).json()['needs_legal_consent'] is True
    other=account(client,'owner');c=create_case(client,other)
    assert client.put(f'/api/cases/{c["id"]}/like',headers=headers).status_code==403
    assert client.post('/api/me/legal-consent',headers=headers,json=LEGAL_FIELDS).status_code==200
    assert client.put(f'/api/cases/{c["id"]}/like',headers=headers).status_code==200
    own_case=create_case(client,headers)
    client.post(f'/api/cases/{c["id"]}/comments',headers=headers,json={'content':'Nội dung cũ cần ngừng hiển thị'})
    assert client.post('/api/me/withdraw-consent',headers=headers).status_code==200
    assert client.get('/api/me',headers=headers).status_code==401
    assert client.post('/api/auth/login',json={'username':'legacy','password':'test-password-123'}).status_code==403
    assert client.get(f'/api/cases/{own_case["id"]}').status_code==404
    assert client.get(own_case['image_url']).status_code==404
    assert 'Nội dung cũ cần ngừng hiển thị' not in client.get(f'/api/cases/{c["id"]}/comments').text

def test_legal_pages_and_private_request_intake(client,monkeypatch):
    monkeypatch.setenv('LEGAL_OPERATOR_NAME','<script>alert(1)</script>')
    for path in ['/terms','/privacy','/copyright','/support','/guardian-consent']:
        response=client.get(path)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert '<script>alert(1)</script>' not in response.text
        assert '&lt;script&gt;' in response.text
    data={'kind':'copyright','name':'Chủ tác phẩm','email':'rights@example.com','content_url':'/api/cases/1','details':'Tôi là tác giả của bức ảnh, xin kiểm tra quyền sử dụng ảnh.','contact_consent':True}
    assert client.post('/api/legal/requests',json={**data,'contact_consent':False}).status_code==422
    refs=[]
    for _ in range(5):
        response=client.post('/api/legal/requests',json=data)
        assert response.status_code==201;refs.append(response.json()['reference'])
    assert len(set(refs))==5 and all(len(ref)==24 for ref in refs)
    assert client.post('/api/legal/requests',json=data).status_code==429
    assert client.get('/api/legal/requests').status_code==405
