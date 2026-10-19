import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app

@pytest.fixture
def client():
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
    r = client.post('/api/auth/register', json={'username': username, 'password': 'test-password-123', 'email': f'{username}@example.com'})
    assert r.status_code == 201, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}

def create_case(client, headers, **extra):
    stream = io.BytesIO()
    image = Image.new('RGB', (64, 48), 'green')
    exif = Image.Exif()
    exif[270] = 'Private original metadata'
    image.save(stream, 'JPEG', exif=exif)
    r = client.post('/api/uploads', headers=headers, files={'file': ('secret-location.jpg', stream.getvalue(), 'image/jpeg')})
    assert r.status_code == 201
    url = r.json()['image_url']
    clean = Image.open(io.BytesIO(client.get(url).content))
    assert not clean.getexif()
    body = dict(title='Góc phố bí ẩn', answer='Chợ Bến Thành', image_url=url, **extra)
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
    assert client.post('/api/auth/register', json={'username': 'OWNER', 'password': 'test-password-123', 'email': 'another@example.com'}).status_code == 409
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'test-password-123'}).status_code == 200
    c = create_case(client, owner)
    assert client.post('/api/cases', headers=player, json={'title': 'Another', 'answer': 'Somewhere', 'image_url': c['image_url']}).status_code == 400
    assert client.post('/api/auth/logout', headers=player).status_code == 204
    assert client.get('/api/me', headers=player).status_code == 401
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200

def test_contact_registration_profile_and_privacy(client):
    base = {'username': 'tester', 'password': 'test-password-123'}
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
    uploaded = client.post('/api/me/avatar', headers=player, files=files)
    assert uploaded.status_code == 200
    avatar_url = uploaded.json()['avatar_url']
    assert avatar_url.startswith('/uploads/avatar-')
    clean = Image.open(io.BytesIO(client.get(avatar_url).content))
    assert clean.size == (512, 512) and not clean.getexif()
    assert client.get('/api/me', headers=owner).json()['avatar_url'] is None
    assert client.patch('/api/me', headers=player, json={'avatar_url':'https://example.com/track.jpg'}).status_code == 422
    assert client.post('/api/cases', headers=player, json={'title':'Somewhere', 'answer':'A place', 'image_url':avatar_url}).status_code == 400
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
