# Phase 2：Web OAuth 與加密 token

## 本階段可驗證的結果

新的 `app.web:app` 提供 `/login`、`/auth/google`、`/auth/google/callback`。成功回呼會驗證 Google 身分，依 Google `sub` 建立／更新 User 與 OAuthAccount，將 access／refresh token 加密存入多人資料庫，接著 redirect 到固定的 `/auth/complete`。

**這不是完整登入系統。** `/auth/complete` 是公開的靜態階段提示，不證明訪客已登入，也不包含使用者資料。正式 session、登入後 `/dashboard` 與登出留到 Phase 3。本階段不掛載舊的公告、統計、同步、AI、scrape routes，也不下載 Gmail。

## 本機執行

1. 先確認 `.env` 已設定 Web application client 的 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`，以及：

   ```dotenv
   GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
   APP_BASE_URL=http://localhost:8000
   ```

2. 補齊本機設定：

   ```powershell
   .\.venv\Scripts\python.exe -m app.auth.setup_local
   ```

   此指令只在缺少設定時產生 Fernet 金鑰與新的 SQLite 路徑，保存至 `.env`，不輸出密鑰；不替換已存在的 key。**保留並安全備份 TOKEN_ENCRYPTION_KEY**，否則已保存的 token 無法解密。環境變數優先於 `.env`；如設定來自程序環境，需確保之後啟動服務時仍存在。

3. 對新資料庫執行 migration：

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m alembic current
   ```

   預期 revision 是 `0002`。新增 `oauth_attempts` 儲存短暫 OAuth 交易，不是 authenticated session 表。不要指定舊資料庫路徑。

4. 啟動獨立 OAuth 測試入口：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.web:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
   ```

   開啟 `http://localhost:8000/login`。主機固定使用 localhost，避免與 127.0.0.1 的 cookie 混用。伺服器需要連外至 Google token endpoint 與簽章憑證 endpoint。不要使用會輸出完整 HTTP body 的 debug logging。

5. 用 Test users 內的帳號完成同意，確認瀏覽器轉往 `/auth/complete`；只回報結果或錯誤代碼，不分享 callback 網址、code、token 或 Client Secret。

正式部署需另行處理 HTTPS、反向代理、session、帳號存取政策與 Google verification，尚未在本階段完成。

## 安全與資料流

- Scopes 固定為 `openid email profile` 與 `gmail.readonly`；Google 回傳的 userinfo scope 別名會正規化。缺少必要 scope 或包含 Gmail send／modify 等額外 scope 都拒絕保存。原 Desktop OAuth 的 scope 檢查不變。
- 授權 URL 使用隨機 state、nonce、PKCE S256、offline access。state 在 DB 只存雜湊，PKCE verifier／nonce 加密存放，10 分鐘到期。瀏覽器只保存 HttpOnly、SameSite=Lax 的隨機綁定 cookie；HTTPS 環境自動 Secure。一次只支援目前瀏覽器最新一次授權流程。
- callback 透過原子 DELETE RETURNING 消耗交易，綁定 state 與瀏覽器；跨瀏覽器、逾時與重放都拒絕。消耗完成才聯絡 Google，即使 Google 暫時失敗也必須重新從 `/login` 開始。
- ID token 由 google-auth 驗證簽章、issuer、audience、expiry、issued-at；另驗證 nonce、email_verified、sub、azp 與存在時的 at_hash。以 sub 對應帳號，不以同 email 自動合併。
- Fernet 加密內容綁定 user ID、provider 及 token 類型，不能將另一個 user 的密文直接搬過來使用。token 不會放入 HTML、JS、localStorage、cookie 或回應 JSON。

## Token service 行為

`app/auth/token_service.py` 提供 encrypt、decrypt、access_token（含 refresh）與 revoke。

| 情況 | 行為 |
| --- | --- |
| 登入回傳 refresh token | 加密後保存 |
| 已存在帳號登入未回傳 refresh token | 保留原本可解密的 refresh token |
| 首次授權沒有 refresh token | 回滾 User／OAuthAccount 寫入，要求重新授權 |
| Access token 60 秒內到期 | 呼叫 Google refresh；加密保存新 token 與 expiry |
| Refresh 回傳 invalid_grant | 拋出固定 `OAUTH_REAUTHORIZE`；不破壞原資料，後續同步入口需提示重新登入 |
| Google 暫時故障或逾時 | 固定 provider error，不將 response body／credentials 放入錯誤 |
| 撤銷成功 | 清空該 user 的加密 token；尚無公開 revoke route |
| 撤銷失敗 | 保留資料，讓使用者之後重試 |

Refresh 使用 PostgreSQL row lock 與條件式更新防止覆蓋不同版本的憑證；SQLite 的競爭寫入可能回報資料庫忙碌，呼叫端需要重試。真實 PostgreSQL concurrency 驗證留在後續階段。一般登出只應清除網站 session，不自動 revoke Google token。

## 日誌與錯誤

啟動命令預設關閉 access log；程式也為標準 Uvicorn access record 加上 query redaction，以免 callback code 被記錄。未預期的 request 錯誤只返回固定代碼，不向 ASGI server 傳出含 SQL／provider 內容的例外。未來反向代理也必須停用或遮蔽 callback query logging；應用程式無法控制代理的日誌設定。

`/auth/complete` 不輸出 email、user ID 或 token。回呼處理後刪除短暫 cookie，HTTP 回應使用 no-store、no-referrer 與 CSP。

## 修改檔案與驗證

新增 `app/auth/`（config、google_oauth、token_service、attempts、errors、setup_local）、`app/api/auth.py`、`app/web.py`、migration `0002` 及 `tests/test_auth.py`；更新多人 model、requirements、`.env.example` 與 README。

測試完全使用合成資料／HTTP transport mock；ID token 測試以臨時 RSA key 產生真實簽章，再由 google-auth 驗證，沒有繞過簽章驗證。涵蓋 cookie/state/重放/到期、scope、身分 claim、加密、refresh、revoke、舊資料隔離，以及 migration metadata 一致性。

離線 pytest 不代表 Google Cloud 設定已成功。必須另外在瀏覽器完成真實 Google consent，才能確認該 Client 的設定與授權結果。

參考：[Google Web Server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)、[Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)、[Fernet](https://cryptography.io/en/latest/fernet/)。
