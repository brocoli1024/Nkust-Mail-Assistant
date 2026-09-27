# Phase 3：登入 Session 與登出

## 本階段行為

正式本機入口仍是 `app.web:app`。`/login` 顯示登入頁，Google callback 成功後換發 session 並導向 `/dashboard`。Dashboard 目前只有帳號與功能準備中的提示，尚未同步或顯示公告。`/settings` 顯示目前帳號與登出表單。

未登入開啟 Dashboard／Settings 會導向 `/login`；`/api/me` 和 `POST /logout` 回傳 401。不存在的舊公告、AI、同步與擷取 routes 保持 404，不能透過它們繞過登入。

## Session 與 cookie

選用 SQL 資料庫保存的 server-side session，因為可立即撤銷，且多個 worker／服務重新啟動後共享同一份登入狀態。每次成功登入產生 256-bit 隨機識別碼；cookie 只存該值，資料庫 `web_sessions` 只存 SHA-256 雜湊、user_id、建立時間與到期時間，不存 Google token。

Session 固定 8 小時到期、不滑動延長；每次讀取都檢查到期時間與 User 是否存在。登入時撤銷目前瀏覽器舊 session 並換發新值；其他瀏覽器仍可維持各自登入。過期資料在建立新 session 時清理。

| 設定 | 本機 HTTP | 正式 HTTPS |
| --- | --- | --- |
| Cookie 名稱 | `nkust_session` | `__Host-nkust_session` |
| HttpOnly | 是 | 是 |
| Secure | 否，僅限 localhost 開發 | 是 |
| SameSite | Lax | Lax |
| Path／Domain | `/`，不設定 Domain | `/`，不設定 Domain |

`SESSION_SECRET` 用來衍生與 session 綁定的 CSRF token，至少 32 bytes；setup_local 缺少時會產生隨機值，不輸出或覆寫既有值。更換此 secret 會讓舊頁面的 CSRF token 失效，但不會撤銷 session；若要強制所有人登出，需另行撤銷 DB sessions。

## 登出

只接受 `POST /logout`。表單傳送 hidden CSRF token；API 呼叫也可使用 `X-CSRF-Token`。token 使用 HMAC 與目前 session 綁定，以 constant-time comparison 驗證；並拒絕不符 APP_BASE_URL 的 Origin 及 cross-site fetch。

登出成功會刪除 DB session、清除 cookie 與待完成 OAuth 的瀏覽器 cookie，再導回登入頁顯示完成提示。即使重放舊 session cookie 也無法存取資料。**不會撤銷 Google token、刪除帳號或影響其他瀏覽器。**

## 程式邊界

新增 `app/core/session.py`、`app/api/session.py`、Jinja2 templates、獨立 CSS 與 migration `0003`；更新 OAuth callback、web entry point、setup_local 與依賴。`current_user` dependency 用於 API，`current_page_user` 用於頁面；後續 Phase 4–6 必須透過這個身分取得 OAuth account、同步與查詢公告，不接受前端指定的 user_id。

`create_app()` 的預設仍保留 Phase 2 OAuth-only 工廠介面，讓既有 Phase 2 測試不需改寫；它不掛載任何私有資料頁面。模組公開的 `app.web:app` 明確使用 `session_enabled=True`。新測試／自訂部署若呼叫工廠，務必指定 `session_enabled=True`。舊 `app.main:app` 仍只適用單人本機版。

## 操作與驗證

1. 用 `python -m app.auth.setup_local` 補齊缺少的 SESSION_SECRET；保留 TOKEN_ENCRYPTION_KEY。
2. 先備份新的多人資料庫，再執行 `python -m alembic upgrade head`；預期 revision `0003`。不要將 DATABASE_URL 指向舊 SQLite。
3. 啟動 `python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers`。
4. 開啟 `http://localhost:8000/login`，登入後應進入 Dashboard；按「登出」後再次開啟 Dashboard 應回到登入頁。Phase 2 的 Google 授權不會自動變成網站 session，需重新登入一次。
5. `python -m pytest -q` 執行既有與新增測試。

新增測試涵蓋未登入、cookie 屬性、hash 儲存、session 輪替、過期／偽造／已撤銷 session、CSRF、兩位使用者、跨實例撤銷、刪除帳號、HTML escaping 與登出不影響 Google credential。Google consent 的真實瀏覽器驗證仍須由使用者完成。

本階段沒有進入 per-user Gmail service（Phase 4）、同步（Phase 5）或公告 ownership filtering（Phase 6）。
