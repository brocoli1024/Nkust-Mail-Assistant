"""Disposable loopback-only synthetic preview. Never load production credentials."""
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from alembic import command
from sqlalchemy.engine import URL
from cryptography.fernet import Fernet
from fastapi.responses import RedirectResponse,HTMLResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import Settings
from app.auth.config import OAuthSettings
from app.database.multi_user import MultiUserDatabase
from app.models.multi_user import User,Email,Announcement
from app.models.public_announcements import PublicAnnouncement
from app.services.source_history import record_public_version,record_private_version
from app.web import create_app
from tests.test_auth import FakeGoogle
from tests.test_multi_user_database import configuration
import uvicorn

scratch=tempfile.TemporaryDirectory(prefix='nkust-action-card-qa-')
url=URL.create('sqlite',database=str(Path(scratch.name)/'synthetic.db'))
command.upgrade(configuration(url),'head')
db=MultiUserDatabase(url)
with db.transaction() as s:
    s.add_all([User(id=1,google_user_id='google-a',email='a@example.invalid'),User(id=2,google_user_id='google-b',email='b@example.invalid')]);s.flush()
    for uid in (1,2):
        s.add(Email(id=uid,user_id=uid,gmail_message_id=f'qa-{uid}',status='processed',received_at=datetime(2026,10,29,tzinfo=timezone.utc)))
    s.flush()
    for uid in (1,2):
        s.add(Announcement(id=uid,user_id=uid,email_id=uid,source_index=0,source_fingerprint=str(uid)*64,department='合成測試',source_category='活動',title=f'合成私人公告{uid}',url='https://www.nkust.edu.tw/p/406-1000-12345.php',original_html=f'<p>合成 PRIVATE-{uid}</p>',original_text=f'PRIVATE-{uid}：請繳交報告。報名截止：2026年11月12日。活動日期：2026年11月20日。'))
    s.add(PublicAnnouncement(id=1,source_key='nkust-latest',canonical_url='https://www.nkust.edu.tw/p/406-1000-12345.php',title='【合成驗收】申請活動',excerpt='請報名參加。申請對象：全校學生。應備文件：在學證明。報名截止：2026年11月10日；活動日期：2026年11月20日。',content_hash='qa-public'))
    s.flush()
    now=datetime.now(timezone.utc)
    for uid in (1,2):record_private_version(s,s.get(Announcement,uid),s.get(Email,uid),now)
    p=s.get(PublicAnnouncement,1);record_public_version(s,p,now)
    p.excerpt=p.excerpt.replace('11月10日','11月11日');record_public_version(s,p,now)
db.close()
oauth=OAuthSettings('qa-client','qa-secret','http://127.0.0.1:8766/auth/google/callback','http://127.0.0.1:8766',Fernet.generate_key().decode())
app=create_app(Settings(database_url=url),oauth,google_factory=FakeGoogle,session_enabled=True,demo_enabled=True,session_secret='synthetic-qa-session-secret-at-least-32-characters')
original_lifespan=app.router.lifespan_context
@asynccontextmanager
async def lifespan(app):
    async with original_lifespan(app):
        app.state.sessions.cookie_name='nkust_qa_session'
        yield
app.router.lifespan_context=lifespan
@app.get('/__qa')
def start():
    return HTMLResponse('<h1>僅合成資料：第五階段驗收</h1><a href="/public/announcements/1">公開合成公告</a><br><a href="/demo/announcements/demo-event">示範</a><br><a href="/__qa/login/1">登入合成帳號 A</a><br><a href="/__qa/login/2">登入合成帳號 B</a><br><a href="/__qa/harness">儲存測試</a><br><a href="/__qa/change-public">變更合成公開來源</a>')
@app.get('/__qa/login/{uid}')
def login(uid:int):
    if uid not in (1,2):return HTMLResponse('Not found',status_code=404)
    value=app.state.sessions.create(uid)
    r=RedirectResponse(f'/announcements/{uid}',status_code=303);app.state.sessions.set_cookie(r,value);return r
@app.get('/__qa/change-public')
def change_public():
    with app.state.database.transaction() as s:
        s.get(PublicAnnouncement,1).excerpt='來源變更的合成內容，活動日期與材料待確認。'
    return RedirectResponse('/public/announcements/1',status_code=303)
@app.get('/__qa/harness')
def harness():return FileResponse(Path(__file__).with_name('action_card_store.html'))
@app.get('/__qa/todos-harness')
def todo_harness():return FileResponse(Path(__file__).with_name('todo_store.html'))
app.mount('/__qa/assets',StaticFiles(directory=Path(__file__).parent))
if __name__=='__main__':
    try:uvicorn.run(app,host='127.0.0.1',port=8766,access_log=False)
    finally:scratch.cleanup()
