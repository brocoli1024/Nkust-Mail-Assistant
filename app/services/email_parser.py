"""Decode Gmail full-message payloads without making network calls directly."""
import base64
import binascii
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime


class EmailParseError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedEmail:
    gmail_message_id: str
    sender: str
    subject: str
    received_at: datetime
    html_body: str | None
    text_body: str | None

    @property
    def preferred_body(self) -> str:
        return self.html_body if self.html_body is not None else (self.text_body or '')


def _headers(part: dict) -> dict[str, str]:
    return {item['name'].lower(): item['value'] for item in part.get('headers', [])}


def _decode_data(data: str, charset: str) -> str:
    try:
        raw = base64.b64decode(data + '=' * (-len(data) % 4), altchars=b'-_', validate=True)
        return raw.decode(charset)
    except (ValueError, UnicodeError, LookupError, binascii.Error) as exc:
        raise EmailParseError('MIME_DECODE_ERROR: invalid base64url or character encoding') from exc


def _bodies(part: dict, attachment_loader: Callable[[str], str] | None):
    headers = _headers(part)
    if part.get('filename') or headers.get('content-disposition', '').lower().startswith('attachment'):
        return None, None
    mime = part.get('mimeType', '').lower()
    if mime.startswith('multipart/'):
        alternatives = [_bodies(child, attachment_loader) for child in part.get('parts', [])]
        def combine(index):
            values = [item[index] for item in alternatives if item[index] is not None]
            if not values:
                return None
            # RFC alternative parts are variants, not additional announcements.
            return values[-1] if mime == 'multipart/alternative' else '\n'.join(values)
        return combine(0), combine(1)
    if mime not in ('text/html', 'text/plain'):
        return None, None
    body = part.get('body', {})
    data = body.get('data')
    if data is None and body.get('attachmentId'):
        if attachment_loader is None:
            raise EmailParseError('MIME_ATTACHMENT_REQUIRED: body needs Gmail attachment retrieval')
        try:
            data = attachment_loader(body['attachmentId'])
        except Exception as exc:
            raise EmailParseError('MIME_ATTACHMENT_ERROR: could not retrieve body') from exc
    if data is None:
        if body.get('size', 0):
            raise EmailParseError('MIME_BODY_MISSING: nonempty body has no data')
        data = ''
    message = Message()
    message['Content-Type'] = headers.get('content-type', mime)
    decoded = _decode_data(data, message.get_content_charset() or 'utf-8')
    return (decoded, None) if mime == 'text/html' else (None, decoded)


def decode_message(message: dict, attachment_loader: Callable[[str], str] | None = None) -> DecodedEmail:
    try:
        payload = message['payload']
        headers = _headers(payload)
        if 'internalDate' in message:
            received_at = datetime.fromtimestamp(int(message['internalDate']) / 1000, timezone.utc)
        else:
            received_at = parsedate_to_datetime(headers['date'])
            if received_at.tzinfo is None:
                raise EmailParseError('EMAIL_DATE_ERROR: received date has no timezone')
        html, plain = _bodies(payload, attachment_loader)
        if html is None and plain is None:
            raise EmailParseError('MIME_BODY_MISSING: no supported message body')
        return DecodedEmail(
            message['id'], str(make_header(decode_header(headers.get('from', '')))),
            str(make_header(decode_header(headers.get('subject', '')))), received_at,
            html, plain,
        )
    except EmailParseError:
        raise
    except (KeyError, ValueError, TypeError, OverflowError, LookupError) as exc:
        raise EmailParseError('EMAIL_FORMAT_ERROR: invalid Gmail message metadata') from exc
