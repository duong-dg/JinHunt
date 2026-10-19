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
    r = client.post('/api/auth/register', json={'username': username, 'password': 'test-password-123'})
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
    assert client.post('/api/auth/register', json={'username': 'OWNER', 'password': 'test-password-123'}).status_code == 409
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'owner', 'password': 'test-password-123'}).status_code == 200
    c = create_case(client, owner)
    assert client.post('/api/cases', headers=player, json={'title': 'Another', 'answer': 'Somewhere', 'image_url': c['image_url']}).status_code == 400
    assert client.post('/api/auth/logout', headers=player).status_code == 204
    assert client.get('/api/me', headers=player).status_code == 401
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
