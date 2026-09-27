# Phase 8：PostgreSQL 遷移準備

使用者確認本機尚未安裝 PostgreSQL，本階段只完成準備，不安裝、不切換 DATABASE_URL、不匯入真實資料。目前網站繼續使用 SQLite。

## 相容性與驗證範圍

- SQLAlchemy 使用 psycopg 3；postgresql:// 自動正規化為 postgresql+psycopg://，保留 sslmode 等連線參數。密碼特殊字元須做 URL encoding，連線字串只放環境變數或忽略提交的 .env。
- Alembic 0001–0004 已提供 PostgreSQL 離線升級／降級 SQL；時間欄位為 TIMESTAMP WITH TIME ZONE、日期 Date、JSON、Boolean、整數自動序列。複合 owner 外鍵與每帳號 Gmail ID 唯一限制保留。
- Dashboard 以台灣午夜換算 UTC 後比較，沒有 SQLite 專屬日期函式。同步 lease 採 PostgreSQL ON CONFLICT 與 UPDATE fencing；真正並行行為仍須實機確認。
- 新增離線 tests/test_postgresql_readiness.py 與 opt-in tests/test_postgresql.py。SQL 編譯成功不能取代實際執行。

## 將來啟用 PostgreSQL 測試

1. 準備**獨立、無正式資料**的測試 database 與非 superuser 帳號，允許該帳號在此 database 建立 schema。不要使用正式站連線。
2. 將 `NKUST_TEST_POSTGRES_URL` 設為程序環境變數，值為 `postgresql+psycopg://USER:URL_ENCODED_PASSWORD@HOST:5432/TEST_DATABASE`。遠端連線依提供者要求使用 TLS／CA（例如 sslmode=verify-full）。不要貼密碼到聊天或 Git。
3. 執行 `.\.venv\Scripts\python.exe -m pytest tests/test_postgresql.py -q`。此入口不讀取 .env 的測試變數，不會借用應用程式 DATABASE_URL。未設定時明確 skip；設定後連線失敗會 fail。
4. 每個案例建立 UUID 命名的 `nkust_test_...` schema，使用獨立 search_path 執行真實 migration。結束只清理它自己建立的 schema（含測試資料），不刪 database 或 public schema。異常中斷可能留下一個測試 schema，需人工確認後清理。

實機案例包含 schema 與 models 比對、重複 upgrade、downgrade／re-upgrade（只限拋棄式 schema）、自動 ID、unique／owner 外鍵／cascade、真實 parser 與同步儲存、失敗重試，以及兩個連線搶同一 lease 只有一個成功。

## 正式資料遷移方案（尚未執行）

Alembic 只遷移 schema，**不會把 SQLite 資料自動複製進 PostgreSQL**。切換前另行確認資料搬移範圍與演練。

1. 暫停同步及寫入，用 SQLite backup API 產生一致備份，驗證可開啟、資料筆數與完整性；另妥善備份 TOKEN_ENCRYPTION_KEY 與 SESSION_SECRET，不將金鑰放進資料庫備份或 Git。
2. 在空的 PostgreSQL 目的庫執行 Alembic upgrade head。先用合成資料驗證，再在演練環境匯入備份副本。
3. 新多人 SQLite 依原 users.id 與 Google subject 保留所有 owner 關聯；逐表按 FK 順序搬移。保留加密 token 需要原加密金鑰及原 user ID；如果改 ID，必須重新加密其 owner 綁定內容。不要複製 OAuth attempts、Web sessions 或 sync leases，切換後重新登入。
4. 舊單人 `data/nkust_mail.db` 必須另行指定經確認的目標帳號，不能自動歸屬「第一位使用者」，也不能只依 email 合併。舊 token.json 不直接當成多人帳號憑證。匯入公告前必須處理同 Gmail ID 去重及 email／announcement ID 對映。
5. 匯入保留顯式整數 ID 時，重設每張有自動 ID 的 PostgreSQL sequence 至資料最大值；SQLite 的自動 ID 行為不可直接套用。檢查 FK、每使用者筆數、Unicode、JSON、UTC 時間、NULL／Boolean、Dashboard 日期與 token 解密。驗證後才切換 DATABASE_URL、啟動、登入並手動同步。

回復：在切換驗收期間維持原 SQLite 備份不變。若需回切，先停寫 PostgreSQL，再還原舊連線設定與相同金鑰。切換後新增資料不會自動回到 SQLite，需先匯出／對帳，不能宣稱直接回切無資料損失。不要以 downgrade 當資料回復策略。

## 階段界線

完成項：離線 SQL／查詢與連線設定檢查、可啟用的隔離實機測試、備份及搬移方案。

未完成項：真實 PostgreSQL 執行、資料匯入工具與演練、實際資料切換、部署。這些需要後續獨立測試環境與確認；本階段未進入 Phase 9。

最終測試：312 passed、9 skipped（全部為未設定測試連線的 PostgreSQL 實機案例），2 個既有棄用警告。原單人資料庫與 token.json SHA256 不變；沒有修改應用程式碼或連線設定，因此不需重啟。
