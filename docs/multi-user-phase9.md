# Phase 9：部署準備（尚未上線）

目前沒有指定正式主機或網域，也尚未安裝 PostgreSQL。此階段提供平台中立操作手冊與唯讀檢查工具，不建立雲端資源、不公開本機網站、不改 Google Cloud 或 .env。不加入 Docker production、PWA、AI 或背景同步。

## 執行入口

多人服務只能啟動 `app.web:app`；`app.main:app` 是舊單人服務，不適合作為多人網站入口。使用獨立 Python 虛擬環境，以 `requirements-lock.txt` 安裝鎖定相依套件。此檔案仍包含舊版 AI／Scrapling 相依；它們不會由多人 routes 啟用。正式主機的 Python 與套件相容性須另行驗證。

部署包須排除 .env、token.json、credentials.json、SQLite、備份、私人郵件樣本與本機 .venv。環境變數由主機的 secret 管理注入；不得放进前端、啟動命令參數或公開 Git。

## 設定

必要變數見 .env.example：DATABASE_URL、GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、GOOGLE_REDIRECT_URI、APP_BASE_URL、SESSION_SECRET、TOKEN_ENCRYPTION_KEY。正式 APP_BASE_URL 使用實際 HTTPS 網域，callback 必須完全等於該網址加 `/auth/google/callback`。金鑰只產生一次，安全備份；每次發布重新產生會使現存 token 無法解密或 session CSRF 失效。

正式資料庫使用 postgresql+psycopg。依供應商配置 TLS／CA、網路規則、最小權限帳號、備份與連線逾時。web 啟動及 schema migration 不會自行搬移 SQLite；資料搬移計畫見 Phase 8。先在獨立測試庫跑 PostgreSQL 整合案例，全部通過後才考慮正式切換。

## 發布流程

1. 在測試環境安裝鎖定套件，執行完整 pytest 及指定 PostgreSQL 測試；9 項 skip 不算實機通過。於目標環境另做相依漏洞掃描、備份還原演練。
2. 備份目的庫和所需金鑰，再於**確認的新多人庫**執行 `python -m alembic upgrade head`。migration 由單一發布工作執行，不由每個 web worker 同時執行。不得使用 downgrade 當資料回復。
3. 執行 `python -m app.deployment_check`。退出碼 0 僅表示基本設定及 revision 0004 可讀；退出碼 1 列固定問題代碼，不輸出秘密。工具不驗證 Google client 真實可用、TLS、DNS、OAuth 發布狀態、金鑰熵、既有 token 能否解密或完整 schema 差異。當前 localhost／SQLite 設定被拒絕是預期結果。
4. 在有 HTTPS 反向代理的同機環境啟動：`python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --no-proxy-headers`。此命令只適用同機代理。雲端平台若要求指定 PORT／bind 位址，待選定平台後提供相應設定，不直接照搬此命令。
5. 由代理保留正確 Host、終止 TLS、將 HTTP 導向 HTTPS；不公開後端埠。此版依 APP_BASE_URL 設定 Secure Cookie／Origin，不依任意 forwarded header。所有層級（日誌、APM、代理）都應排除 OAuth code/state、cookie、Authorization、請求本文；Uvicorn 不記 access log 不代表代理也已停記。不得快取登入、公告、同步與錯誤頁。

## 負載與探測

目前同步在請求期間完成；每帳號 lease 阻止重複作業，但不同帳號仍會佔用執行資源。初次上線限小量測試帳號，代理設定請求大小上限、速率／連線限制與適當逾時；實際值須在主機負載測試後決定。不可把增加 worker 當成已完成容量驗證。

服務管理交由主機 supervisor，自動重啟並提供受限權限。以正確 Host 對 `/login` 做基本 HTTP 存活探測（預期 200）；此探測不代表 DB／Google 可用。DB readiness 可由受控部署工作執行 preflight，不要對外公布含連線細節的 debug endpoint。

## Google Cloud：選定網域後才操作

尚未選定正式網域，現在不需更改。

選定後到 Google Cloud Console 對應專案的 Google Auth Platform／OAuth client 設定，選現有 Web application client，在 Authorized redirect URIs 加入實際的 `https://正式網域/auth/google/callback`，並與環境變數完全一致。保留開發用途的 localhost callback。介面位置与發布／驗證要求屆時依官方文件確認，不假設測試模式可直接服務所有學生。需準備適用的隱私政策、資料保存／刪除方式與 OAuth 授權說明；gmail.readonly 對外發布相關要求尚未驗證。

## 上線驗收與回復

透過真實 HTTPS 網域驗證 Google 登入、Secure／HttpOnly／SameSite cookie、登出、兩帳號隔離、手動同步、重複同步、原文頁和過期授權。確認代理日誌不記秘密，測試失敗時不切流量。Phase 7 的自動測試不取代這些驗收。

保留上一版程式、相容 schema 和資料備份。回復程式前先確認 migration 相容性；若需還原資料庫，先停寫並處理新資料對帳。避免把新寫入直接丟棄。未完成 PostgreSQL 實機、正式 OAuth、TLS／代理、備份還原與容量驗證前，不宣稱 production-ready。

本階段完成後停在 Phase 9；PWA 屬 Phase 10，必須另行確認。

## 本階段驗證結果

完整 pytest：317 passed、9 skipped（PostgreSQL 未設定）、2 個既有棄用警告。新增的 5 項 preflight 測試通過。本機實際執行 preflight 回退出碼 1，代碼 PUBLIC_HTTPS_REQUIRED／POSTGRESQL_REQUIRED，符合目前 HTTP localhost＋SQLite 的狀態。git diff --check 通過；舊資料庫與 token.json SHA256 不變。沒有修改現行 .env、web routes 或 schema，不需重啟本機服務。
