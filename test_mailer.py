import asyncio
from email.message import EmailMessage
from types import SimpleNamespace

from server.db import Database
from server.mailer import InboundHandler, extract_message, local_from_address


def test_address_validation():
    assert local_from_address('Test_123@EXAMPLE.org','example.org')=='test_123'
    assert local_from_address('test123@other.org','example.org') is None
    assert local_from_address('x@y@example.org','example.org') is None
    assert local_from_address('invalid+tag@example.org','example.org') is None
    assert local_from_address('bad..name@example.org','example.org') is None
    assert local_from_address('bad.@example.org','example.org') is None


def test_mime_and_html_sanitization():
    m=EmailMessage()
    m['From']='Alice <alice@example.net>'
    m['Subject']='Test subject'
    m.set_content('<b>Hello</b> <script>alert("danger")</script><p>Code 789123</p>',subtype='html')
    sender,subject,body,_=extract_message(m.as_bytes())
    assert 'alice@example.net' in sender
    assert subject=='Test subject'
    assert 'Code 789123' in body
    assert 'danger' not in body
    assert '<script>' not in body


def test_smtp_accepts_only_active_alias(settings):
    db=Database(settings.database_path); db.init()
    ident,status=db.create_alias('tester',settings.max_aliases)
    assert status=='ok'
    handler=InboundHandler(db,settings)
    envelope=SimpleNamespace(rcpt_tos=[],mail_from='',mail_options=[],content=b'')
    async def send():
        assert (await handler.handle_MAIL(None,None,envelope,'sender@example.net',[])).startswith('250')
        assert (await handler.handle_RCPT(None,None,envelope,'x@other.org',[])).startswith('550')
        assert (await handler.handle_RCPT(None,None,envelope,'tester@example.org',[])).startswith('250')
        m=EmailMessage();m['From']='Sender <sender@example.net>';m['Subject']='Welcome';m.set_content('Your code is 654321')
        envelope.content=m.as_bytes()
        assert (await handler.handle_DATA(None,None,envelope)).startswith('250')
    asyncio.run(send())
    assert db.list_messages(None,'')[0]['subject']=='Welcome'
    db.set_alias_active(ident,False)
    envelope.rcpt_tos=[]
    assert asyncio.run(handler.handle_RCPT(None,None,envelope,'tester@example.org',[])).startswith('550')


def test_retention_and_storage_limit(settings):
    db=Database(settings.database_path);db.init()
    aid,_=db.create_alias('test999',settings.max_aliases)
    for i in range(20):
        db.save_messages([aid],'sender',f'subj{i}','test','', retention_days=7,max_stored_messages=10)
    assert len(db.list_messages(None,''))==10
