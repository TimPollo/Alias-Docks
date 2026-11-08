def test_health_and_auth(client):
    assert client.get('/healthz').json() == {'ok':True}
    assert client.get('/api/config').json()['alias_domain'] == 'example.org'
    assert client.get('/api/me').status_code == 401
    assert client.get('/api/aliases').status_code == 401
    assert client.post('/api/aliases',json={}).status_code == 401
    assert client.post('/api/login',json={'username':'admin','password':'wrong'}).status_code == 401


def test_end_to_end_inbox(authed):
    c = authed
    result=c.post('/api/aliases',json={'local_part':'newsletter'})
    assert result.status_code == 201, result.text
    a=result.json(); assert a['address']=='newsletter@example.org'
    assert c.post('/api/aliases',json={'local_part':'newsletter'}).status_code == 409
    assert c.post('/api/aliases',json={'local_part':'a'}).status_code == 422
    assert c.post('/api/aliases',json={'local_part':'postmaster'}).status_code == 422
    assert len(c.get('/api/aliases').json()['aliases']) == 1
    from server.db import Database
    from server.config import Settings
    db=Database(c.app.state.cfg.database_path)
    saved=db.save_messages([a['id']], 'Hello <demo@example.net>', 'Test ✉', 'Ihr Code: 123456',
        '<mail1@example.net>', retention_days=14, max_stored_messages=2000)
    assert saved == 1
    assert c.get('/api/stats').json()['unread_count'] == 1
    messages=c.get('/api/messages').json()
    assert len(messages['messages']) == 1
    assert messages['messages'][0]['subject'] == 'Test ✉'
    mid=messages['messages'][0]['id']
    assert c.get(f'/api/messages/{mid}').json()['body'] == 'Ihr Code: 123456'
    assert len(c.get('/api/messages?q=123456').json()['messages']) == 1
    assert c.post(f'/api/messages/{mid}/read').status_code == 200
    assert c.get('/api/stats').json()['unread_count'] == 0
    assert c.patch(f"/api/aliases/{a['id']}",json={'active':False}).status_code == 200
    assert db.recipient_alias_id('newsletter') is None
    assert c.delete(f'/api/aliases/{a["id"]}').status_code == 200
    assert c.get('/api/stats').json()['message_count'] == 0


def test_csrf_and_logout(authed):
    c = authed
    token=c.headers.pop('X-CSRF-Token')
    assert c.post('/api/aliases',json={}).status_code == 403
    assert c.post('/api/logout').status_code == 403
    c.headers['X-CSRF-Token']=token
    assert c.post('/api/logout').status_code == 200
    assert c.get('/api/me').status_code == 401


def test_limit_and_rate(authed):
    for i in range(10):
        response=authed.post('/api/aliases',json={'local_part':f'test{i:03d}'})
        assert response.status_code == 201, response.text
    assert authed.post('/api/aliases',json={'local_part':'test555'}).status_code == 429


def test_search_escapes_like(authed):
    c=authed
    aid=c.post('/api/aliases',json={'local_part':'jane123'}).json()['id']
    from server.db import Database
    db=Database(c.app.state.cfg.database_path)
    db.save_messages([aid], 'from@example.com', 'Percentage%Literal', 'This is safe', '', retention_days=14, max_stored_messages=2000)
    assert len(c.get('/api/messages?q=%25').json()['messages']) == 1
    assert len(c.get('/api/messages?q=_').json()['messages']) == 0


def test_security_headers(client):
    r=client.get('/')
    assert r.status_code==200
    assert 'frame-ancestors' in r.headers['content-security-policy']
    assert r.headers['x-content-type-options']=='nosniff'
