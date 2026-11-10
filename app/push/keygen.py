"""Owner-operated setup. Never emit deployment credentials into captured logs."""
import base64,secrets,sys
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

def create_values():
    key=ec.generate_private_key(ec.SECP256R1())
    encode=lambda value:base64.urlsafe_b64encode(value).decode().rstrip('=')
    return {
        'NKUST_PUSH_VAPID_PUBLIC_KEY':encode(key.public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)),
        'NKUST_PUSH_VAPID_PRIVATE_KEY':encode(key.private_numbers().private_value.to_bytes(32,'big')),
        'NKUST_PUSH_VAPID_SUBJECT':'https://nkust-mail-assistant.onrender.com',
        'NKUST_PUSH_TRIGGER_SECRET':secrets.token_urlsafe(48),
        'NKUST_PUSH_RATE_HASH_KEY':secrets.token_urlsafe(48),
    }

def main(stdin=None,stdout=None):
    stdin=stdin or sys.stdin;stdout=stdout or sys.stdout
    if not stdin.isatty() or not stdout.isatty():
        stdout.write('PUSH_SETUP_REQUIRES_PRIVATE_TERMINAL\n');return 2
    stdout.write('首次推播設定：新金鑰只顯示在此視窗，不寫入檔案。勿貼到聊天、日誌或Git。\n若已有正式VAPID金鑰，請勿重新產生。輸入 GENERATE 再按Enter：');stdout.flush()
    if stdin.readline().strip()!='GENERATE':return 1
    for name,value in create_values().items():stdout.write(name+'='+value+'\n')
    stdout.write('由本人複製到Render；Cloudflare只放同一組NKUST_PUSH_TRIGGER_SECRET。完成後關閉此視窗。\n');return 0
if __name__=='__main__':raise SystemExit(main())
