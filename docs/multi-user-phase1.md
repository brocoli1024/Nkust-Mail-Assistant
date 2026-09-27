# Phase 1：獨立多人資料庫

目前完成 schema 與 migration；沒有接通 Web OAuth、session、per-user sync 或任何多人 Web route。`app.main:app`、CLI 與既有測試仍使用 legacy 模型／資料庫。新增多人模型不是現有公開入口的安全修補，不要將舊 app 公開部署。

## 檔案與邊界

| 檔案 | 責任 |
| --- | --- |
| `app/models/multi_user.py` | 獨立 `MultiUserBase`、User、OAuthAccount、Email、Announcement，以及保留舊資料用的 Analysis／Scrape |
| `app/database/multi_user.py` | URL-based engine、交易、SQLite 外鍵、舊資料庫保護；不呼叫 `create_all()` |
| `alembic/versions/0001_create_isolated_multi_user_schema.py` | 固定的初始 schema；不從可變動的 models 動態建立表 |
| `app/config.py`、`.env.example` | 新增 DATABASE_URL；保留 DATABASE_PATH 與原單人版相容 |
| `tests/test_multi_user_database.py` | 使用臨時 SQLite 跑 migration、隔離約束與回滾；產生 PostgreSQL SQL |

暫時將多人模型集中在一個檔案，避免覆蓋原有 `app.models.email.Email`／`Announcement`。兩套 metadata 只能連向不同資料庫。後續多人程式必須明確 import `app.models.multi_user`，禁止匿名 default user 或 fallback 到 legacy database。

## Schema 規則

- `users.google_user_id` 唯一，以已驗證的 Google `sub` 對應；不靠 email 合併帳號。
- `oauth_accounts` 的 `(provider, provider_user_id)` 及 `(user_id, provider)` 唯一。只預留加密 token 欄位；本階段尚無加解密服務，也不儲存任何真實 token。資料庫欄位名稱本身不能保證內容已加密，Phase 2 必須以 token service 控制寫入。
- Email 的 `(user_id, gmail_message_id)` 唯一，user_id 不可為空。Announcement 的 `(user_id, email_id)` 複合外鍵必須對應同一使用者的 Email；source_index 不可負數且同封信不可重複。
- Analysis／Scrape 也使用 ownership 複合外鍵；保留欄位供未來匯入，不會啟用 AI 或擷取。刪除 user/email 的 CASCADE 是 schema 能力，不代表已建立任何刪除功能。
- 時間採 `DateTime(timezone=True)`，日期採 `Date`，JSON 使用通用 SQLAlchemy JSON。SQLite 回讀 datetime 不保留 timezone，後續資料存取層須按 UTC 正規化；PostgreSQL 使用 TIMESTAMP WITH TIME ZONE。parser 的字串／dataclass 介面保持原樣，在儲存邊界轉換。

索引包含 user_id、received_at、category、deadline；另有 `(user_id, received_at)`、`(user_id, category)`、`(user_id, deadline)` 複合索引。所有 Web 查詢仍必須明確加入 current_user 範圍：外鍵約束只防錯誤寫入，不能限制 SELECT。

## 建立全新的開發資料庫

本階段實作只對 pytest 的臨時資料庫執行 migration，沒有修改真實 `data/nkust_mail.db`，也沒有匯入舊信件。下面是日後建立新開發庫的指令，不是舊資料搬移指令。

1. 在 repository 根目錄安裝依賴：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

2. 明確指定新的 SQLite 路徑（`data` 目錄必須已存在）：

   ```powershell
   $env:DATABASE_URL = 'sqlite:///data/nkust_multi_user.db'
   ```

   也可在 `.env` 設定；process environment 優先。未設定時直接報錯，不會回退到舊資料庫。相對 SQLite 路徑固定以 repository root 解析。

3. 建立新 schema 並檢查 revision：

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m alembic current
   .\.venv\Scripts\python.exe -m alembic check
   ```

   預期 revision 是 `0001`。重複 upgrade 不會清除資料。migration 拒絕預設舊庫路徑、設定中的 DATABASE_PATH，以及缺少 user_id 的 legacy emails／announcements schema。不要使用 `alembic stamp` 繞過保護，也不要用離線產生的 SQL 手動套入舊庫。

4. 執行測試：

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

`downgrade base` 會刪除新 schema 的資料表及內容，只在可丟棄測試庫驗證；不可當作真實資料的備份或復原方式。

## PostgreSQL readiness 範圍

DATABASE_URL 支援 `postgresql+psycopg://USER:PASSWORD@HOST/NEW_DATABASE`；`postgresql://` 也會選用 psycopg。真實值只放環境變數或本機 `.env`，不得 commit。

Phase 1 驗證包含 PostgreSQL 方言的離線 migration SQL、具時區時間欄位、複合外鍵、唯一約束名稱，以及 SQLite schema 與 ORM metadata 無差異。**尚未連線到真實 PostgreSQL server 執行整合測試**；不能把 SQL 產生成功視為 PostgreSQL runtime 驗證。Phase 8 仍需實際驗證 upgrade、CRUD、並行去重、rollback 與查詢時區。

## 舊資料搬移：待另外確認

1. 停止舊程式寫入，以 SQLite backup API 建立一致快照；記錄校驗值、表筆數並驗證 integrity／foreign keys。
2. 建立獨立新庫，在副本演練，不在原庫原地 ALTER 或刪表。
3. 匯入工具必須明確指定經驗證的擁有者 Google sub，不能歸屬給第一個登入的人。舊 token 不匯入，改用新 Web client 重新授權。
4. 保留 Email、Announcement、Analysis、Scrape 的欄位與關聯；檢查日期格式，保留 ID 或建立對應；PostgreSQL 保留 ID 時需校正 sequence。匯入必須可重跑且不重複，任何轉換失敗都不能默默丟資料。
5. 比對筆數與關聯後才切換新入口；保留原庫與备份作為復原來源。真正的匯入工具與執行須另經確認，本 Phase 沒有自動匯入。

下一階段為 Web OAuth；session 資料表與登入狀態管理留到 Phase 3，避免提前固定尚未實作的認證流程。
