from tests.test_sessions import web
from tests.test_auth import oauth
from bs4 import BeautifulSoup

def test_root_opens_announcement_list_preserving_query(web):
    c,_,_,_=web
    r=c.get('/?q=test&category=活動')
    assert r.status_code==303
    from urllib.parse import unquote
    assert unquote(r.headers['location'])=='/public/announcements?q=test&category=活動'

def test_general_interfaces_do_not_link_demo(web):
    c,_,_,_=web
    for path in ('/public/announcements','/login','/todos','/public/announcements/999999'):
        r=c.get(path)
        assert not BeautifulSoup(r.text,'html.parser').select('a[href^="/demo"]')


def test_production_demo_urls_redirect_instead_of_showing_synthetic_data(web):
    from app.web import create_app
    from fastapi.testclient import TestClient
    _,original,google,settings=web
    prod=create_app(settings,original.state.oauth_settings,google_factory=lambda _:google,
        session_enabled=True,session_secret='production-contract-secret-32-characters')
    with TestClient(prod,base_url='http://localhost',follow_redirects=False) as c:
        for path in ('/demo','/demo/announcements/demo-event'):
            r=c.get(path)
            assert r.status_code==303 and r.headers['location']=='/public/announcements'
            assert '合成示範資料' not in r.text
