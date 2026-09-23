import base64
from unittest.mock import Mock

import pytest

from app.services.email_parser import EmailParseError, decode_message


def encoded(text, charset='utf-8'):
    return base64.urlsafe_b64encode(text.encode(charset)).decode().rstrip('=')


def part(mime, text):
    return {'mimeType': mime, 'body': {'data': encoded(text)}}


def message(payload):
    return {'id': 'synthetic-message', 'internalDate': '1789776000000', 'payload': payload}


def test_nested_alternative_mixed_html_preferred():
    attachment = part('text/plain', 'must not appear')
    attachment['filename'] = 'notes.txt'
    payload = {'mimeType': 'multipart/mixed', 'parts': [
        {'mimeType': 'multipart/alternative', 'parts': [
            part('text/plain', '純文字公告'),
            {'mimeType': 'multipart/related', 'parts': [part('text/html', '<p>中文公告</p>')]},
        ]}, attachment,
    ]}
    decoded = decode_message(message(payload))
    assert decoded.preferred_body == '<p>中文公告</p>'
    assert decoded.text_body == '純文字公告'


def test_plain_only_and_urlsafe_unpadded():
    text = '\uffff\n公告\n測試'
    assert '-' in encoded(text) or '_' in encoded(text)
    decoded = decode_message(message(part('text/plain', text)))
    assert decoded.html_body is None
    assert decoded.preferred_body == text


def test_attachment_id_body():
    loader = Mock(return_value=encoded('<table>公告</table>'))
    decoded = decode_message(message({'mimeType': 'text/html', 'body': {'attachmentId': 'body-id'}}), loader)
    assert decoded.html_body == '<table>公告</table>'
    loader.assert_called_once_with('body-id')


def test_attachment_failure_is_explicit():
    payload = message({'mimeType': 'text/plain', 'body': {'attachmentId': 'body-id'}})
    with pytest.raises(EmailParseError, match='ATTACHMENT_REQUIRED'):
        decode_message(payload)
    with pytest.raises(EmailParseError, match='ATTACHMENT_ERROR'):
        decode_message(payload, Mock(side_effect=TimeoutError))


def test_charset_and_headers():
    payload = {'mimeType': 'text/plain', 'headers': [
        {'name': 'Content-Type', 'value': 'text/plain; charset=big5'},
        {'name': 'Subject', 'value': '=?utf-8?b?5YWs5ZGK?='},
        {'name': 'From', 'value': 'sender@example.invalid'},
    ], 'body': {'data': encoded('公告', 'big5')}}
    decoded = decode_message(message(payload))
    assert decoded.subject == decoded.text_body == '公告'
    assert decoded.sender == 'sender@example.invalid'


@pytest.mark.parametrize('payload', [
    {'mimeType': 'text/html', 'body': {'data': '!!!'}},
    {'mimeType': 'application/pdf', 'body': {}},
    {'mimeType': 'text/plain', 'body': {'size': 20}},
])
def test_malformed_body_errors(payload):
    with pytest.raises(EmailParseError):
        decode_message(message(payload))


def test_empty_html_is_still_html():
    decoded = decode_message(message({'mimeType': 'multipart/alternative', 'parts': [
        part('text/html', ''), part('text/plain', 'fallback'),
    ]}))
    assert decoded.preferred_body == ''


def test_alternatives_do_not_duplicate_html():
    decoded = decode_message(message({'mimeType': 'multipart/alternative', 'parts': [
        part('text/html', '<p>variant 1</p>'), part('text/html', '<p>variant 2</p>'),
    ]}))
    assert decoded.html_body == '<p>variant 2</p>'
