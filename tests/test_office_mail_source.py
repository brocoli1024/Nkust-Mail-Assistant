from datetime import datetime
import pytest
from app.services.public_source import PublicSourceError
URL='https://officemail.nkust.edu.tw/Mail/MailView/69929'

def html(body='<p>建工校區施工，請改走東側入口。</p>',recipient='全校學生',subject='合成施工公告'):
    return f'<html><body><div><h3>國立高雄科技大學 總務處 通知</h3><p><a href="https://mail.google.com/">轉寄</a></p><p>受文者：{recipient}</p><p>日期：民國 115 年 11 月 3 日</p><p>主 旨：{subject}</p><p>說 明：</p><div>{body}</div><p>總務處 敬啟</p><p>聯絡人：PRIVATE-FOOTER</p></div></body></html>'.encode()

def test_valid_office_document_keeps_only_explicit_body():
    from app.services.office_mail_source import parse_office_mail
    doc=parse_office_mail(html('<p>【施工影響】</p><p>建工校區施工。</p><br>請改走東側入口。<script>PRIVATE-SCRIPT</script>'),URL)
    assert doc.external_id=='69929' and doc.title=='合成施工公告' and doc.department=='總務處'
    assert doc.published_at.isoformat()=='2026-11-02T16:00:00+00:00'
    assert '建工校區施工' in doc.body and '\n' in doc.body
    assert all(s not in doc.body for s in ['PRIVATE','受文者','轉寄','主 旨'])

@pytest.mark.parametrize('url',['http://officemail.nkust.edu.tw/Mail/MailView/1','https://evil.invalid/Mail/MailView/1',URL+'?token=secret',URL+'#part','https://u:p@officemail.nkust.edu.tw/Mail/MailView/1','https://officemail.nkust.edu.tw/Mail/MailView/0','https://officemail.nkust.edu.tw/Mail/MailView/01','https://officemail.nkust.edu.tw:444/Mail/MailView/1','https://officemail.nkust.edu.tw/Admin'])
def test_invalid_urls_are_rejected_before_network(url):
    from app.services.office_mail_source import fetch_office_mail
    calls=[]
    with pytest.raises(PublicSourceError):fetch_office_mail(url,transport=lambda u:calls.append(u))
    assert calls==[]

@pytest.mark.parametrize('data',[b'<form><input type="password">Login</form>',html(recipient='王小明'),html(recipient='student@example.invalid'),html(body='<p>僅限內部，禁止公開。</p>'),html(body=''),b'\xff',b'x'*(2*1024*1024+1)],ids=['login','person','email','restricted','empty','encoding','oversize'])
def test_nonpublic_invalid_or_unreadable_pages_are_rejected(data):
    from app.services.office_mail_source import parse_office_mail
    with pytest.raises(PublicSourceError):parse_office_mail(data,URL)

def test_response_redirect_and_missing_date_are_explicit():
    from app.services.office_mail_source import fetch_office_mail,parse_office_mail
    with pytest.raises(PublicSourceError,match='OFFICE_MAIL_HTTP_404'):
        fetch_office_mail(URL,transport=lambda u:(404,{'content-type':'text/html'},b'not found'))
    calls=[]
    def redirect(u):calls.append(u);return 302,{'location':'http://127.0.0.1/private'},b''
    with pytest.raises(PublicSourceError):fetch_office_mail(URL,transport=redirect)
    assert calls==[URL]
    doc=parse_office_mail(html().replace('民國 115 年 11 月 3 日'.encode(),b'unknown'),URL)
    assert doc.published_at is None
    assert fetch_office_mail(URL,transport=lambda u:(200,{'content-type':'text/html'},html())).title=='合成施工公告'


def test_restricted_subject_or_inline_description_cannot_be_imported():
    from app.services.office_mail_source import parse_office_mail
    with pytest.raises(PublicSourceError,match='OFFICE_MAIL_NOT_PUBLIC'):
        parse_office_mail(html(subject='機密文件，禁止公開'),URL)
    with pytest.raises(PublicSourceError,match='OFFICE_MAIL_NOT_PUBLIC'):
        parse_office_mail(html().replace('說 明：'.encode(),'說 明：僅限內部，禁止公開。'.encode()),URL)


def test_inline_description_is_kept_in_complete_original():
    from app.services.office_mail_source import parse_office_mail
    data=html().replace('說 明：'.encode(),'說 明：重要限制：學生不得報名。<br>本段也有條件。'.encode())
    body=parse_office_mail(data,URL).body
    assert body.startswith('重要限制：學生不得報名。\n本段也有條件。')
    assert '建工校區施工' in body
