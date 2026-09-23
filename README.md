# NKUST AI 校園郵件智慧助手

目前：第③階段，已加入 FastAPI 與本機 Dashboard。第①階段已完成本機真實唯讀授權及 5 封郵件解析驗證。
功能包含 config、唯讀 Gmail OAuth／搜尋／取信、MIME 解碼、公告與日期解析、SQLite 原子寫入及重複同步防護。
尚未建立 AI 或 Scrapling。

## 1. 本機安裝與離線測試

在專案根目錄開啟 PowerShell。已於 Windows、Python 3.14 測試；建議 Python 3.11 以上。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.cli parse tests/fixtures/nkust_mail_sample.html --received-at 2026-09-19
```

此專案目前已有 `.venv`；在本機直接執行後兩行即可。精確重現已測試套件版本可改用 `requirements-lock.txt`（包含 pytest）。
離線指令不連線 Gmail、不要求 Google 帳號，預期輸出 3 筆公告。
`.txt` 檔也能使用相同 `parse` 指令。未提供收件日且日期缺年份時保留原文與 warning，不使用電腦當前年份。

## 2. Google Cloud 手動設定（約 10–15 分鐘）

1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)，從頂端專案選單建立並選取 `NKUST Mail Assistant` 專案。
2. 開啟 [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)，確認選中剛建立的專案，按「啟用」。
3. 開啟 [Google Auth Platform / Branding](https://console.cloud.google.com/auth/branding)。首次使用按 Get started，填寫應用程式名稱、自己的支援信箱與聯絡信箱。個人 Gmail 選 **External**；在 [Audience](https://console.cloud.google.com/auth/audience) 保持 **Testing**，將實際要讀取信件的 Google 帳號加入 **Test users**。無須發布正式版。
4. 在 [Data Access](https://console.cloud.google.com/auth/scopes) → Add or remove scopes，只新增 `https://www.googleapis.com/auth/gmail.readonly`，儲存。不要加入寄信、修改、刪除或標籤的 scope。
5. 在 [Clients](https://console.cloud.google.com/auth/clients) → Create client，Application type 選 **Desktop app**，名稱可填 `NKUST Local`。建立後下載 JSON，重新命名 `credentials.json` 並放到本專案根目錄（與 README 同層）。**不需要 Web application 或自行設定 redirect URI。**

本機完整位置：

```text
C:\Users\leogo\OneDrive\文件\ChatGPT\Nkust-Mail-Assistant\credentials.json
```

不用把 JSON 或 token 內容貼到對話中。`token.json` 會在本機授權完成後自動建立。
若使用受管理的學校帳號且管理員阻擋授權，需先處理該帳號的管理限制；程式不會繞過。

設定步驟依據 [Google Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) 與 [OAuth consent 設定](https://developers.google.com/workspace/guides/configure-oauth-consent)。

## 3. 設定與真實 Gmail 驗證

需要改設定時，將 `.env.example` 複製為 `.env`，預設值即可讀取指定 NKUST 寄件來源：

```dotenv
GMAIL_QUERY=from:mailoffice@nkust.edu.tw
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
GMAIL_TIMEOUT_SECONDS=30
DATABASE_PATH=data/nkust_mail.db
```

搜尋式中的 `@` 不需要反斜線。搜尋條件位於 config，不在 Gmail service 硬編碼。環境變數優先於 `.env`；相對路徑相對於專案根目錄。
Scope 固定唯讀，不接受環境變數覆寫。已有較大權限的 token 會被拒絕並保留原檔，請用獨立的唯讀 OAuth client/token。

完成 Google Cloud 設定後，在本機手動執行：

```powershell
.\.venv\Scripts\python.exe -m app.cli gmail --limit 5
```

指令會開啟瀏覽器讓你選帳號、確認唯讀權限。等候登入最多 180 秒；逾時後重新執行即可。
每次 API 請求 timeout 預設 30 秒，官方 client 對可重試錯誤最多重試 2 次。
輸出 UTF-8 JSON：郵件 ID、寄件者、主旨、收件時間、各筆公告、warnings／errors。不會存入資料庫。
若沒有符合郵件，輸出空的 `emails`；若郵件格式無法解析，會列出 error 並以非零狀態結束。
`gmail` 指令只預覽，不寫資料庫；需要持久化去重時使用下方 `sync` 指令。

## 4. 解析契約與限制

| 項目 | 行為 |
| --- | --- |
| MIME | 遞迴解碼 multipart/alternative、mixed、related；Base64 URL-safe；尊重 charset，內部使用 Unicode。保留 HTML 與純文字，HTML 優先。正文在 attachmentId 時補取；一般附檔不當正文。 |
| HTML | 以「寄件單位／郵件性質／主旨」表頭定位，支援換欄序、額外欄位與 td 表頭。未知表格、缺欄、空表、合併資料格明確報錯。HTML 存在但錯誤時不偷偷退回純文字。 |
| 純文字 | 僅在沒有 HTML 時解析；每筆依「寄件單位：」「郵件性質：」「主旨：」標籤順序界定，接受半形冒號。未知格式明確報錯。 |
| 原始資料 | 保留 department、source_category、title、original_text、source_index、source_fingerprint。original_text 保留列中所有欄位文字／空白，br 轉換行；HTML 另保留 original_html，完整信件正文仍在 DecodedEmail。 |
| 日期 | 民國年加 1911；無年份以收件的台北年份補足並標記 year_inferred。活動和截止分開判斷；不明角色只保留 evidence，無效／跨年語意／多個同角色日期保守留空並 warning。 |

`source_index` 從 0 開始，涵蓋整封信所有有效公告表格。
`source_fingerprint` v1 = department、source_category、title 各自 NFKC＋合併空白後，序列化 UTF-8 JSON array，再計算 SHA-256。
fingerprint 僅供追蹤，**不作跨郵件去重**。同一封信不同列即使 fingerprint 相同仍保留。
日期使用 `YYYY-MM-DD`；received_at 使用含時區 ISO 8601。此階段日期解析為保守規則，不推論所有自然語言日期。
`url` 僅擷取主旨中的絕對 HTTP(S) 連結，不抓取網頁。

## 5. 檔案與驗收

| 檔案 | 用途 |
| --- | --- |
| `app/config.py`、`.env.example` | 搜尋、路徑、timeout、固定 scope |
| `app/services/gmail_service.py` | OAuth、token、分頁、取信、attachment 正文 |
| `app/services/email_parser.py` | MIME 與字元解碼、郵件 metadata |
| `app/services/announcement_parser.py`、`date_parser.py` | 拆分公告、原文及 fingerprint、日期與依據 |
| `app/cli.py`、`tests/` | 離線／Gmail 命令列入口、合成測資與 pytest |

測試涵蓋需求 A–E，以及欄序變動、巢狀 MIME、attachmentId、日期不確定、分頁和失敗處理。OAuth 測試使用模擬物件，不能取代真實授權驗證。
真實樣本只能放在 `data/samples/private/`（已忽略）。`.env`、credentials、token、私有郵件、`.venv` 均不納入 Git。
目前已用 5 封真實 NKUST 郵件驗證解析，但未逐筆人工核對。其他未知版型仍可能明確失敗，屆時以去識別化測資補上相應 parser 測試。

## 6. 第②階段：SQLite 同步

在專案根目錄執行（已完成 OAuth 設定者可直接使用）：

```powershell
.\.venv\Scripts\python.exe -m app.cli sync --limit 5
```

再次執行相同指令，已完成且 parser 版本相同的郵件會列入 `skipped`，不再取正文或新增公告。
預設資料庫為 `data/nkust_mail.db`，可用 `.env` 的 `DATABASE_PATH` 修改。資料庫及 SQLite journal 檔案已被 Git 忽略。
`--limit` 是本次搜尋檢查的郵件上限，包含已完成的信，不是「再新增 N 封」；若要匯入較早郵件或重試搜尋範圍外的失敗信件，增加 limit 或調整 `GMAIL_QUERY`。

| 統計欄位 | 意義 |
| --- | --- |
| matched / processed / skipped / failed | 本次找到、成功寫入、略過及失敗的郵件數 |
| announcements_written | 本次成功寫入的公告數；重新解析時包含替換的公告，並非淨新增數 |
| warnings / errors | 解析提醒與逐封錯誤，不包含完整郵件正文 |
| database_counts | 資料庫中的郵件、公告與尚未成功的失敗郵件數 |

資料庫核心規則：

1. `emails.gmail_message_id` 唯一；`announcements(email_id, source_index)` 唯一。Fingerprint 僅供追蹤，不作跨郵件合併。
2. 每封信的原文、所有公告及成功狀態在同一交易提交。寫到一半失敗則全部回滾；不同郵件分開提交。
3. 失敗狀態另行記錄，下次選到相同郵件會重試。正文已解碼時保留在 failed 郵件；取信失敗時只記錄 ID 和錯誤。
4. `BEGIN IMMEDIATE` 在檢查及寫入前取得 SQLite 寫入鎖，鎖等待最多 10 秒；唯一限制提供第二層防護。
5. Parser 版本變更時重新解析；也可用 `sync --limit 5 --reparse` 主動重解析。舊公告與新公告在同一交易內替換，失敗保留舊公告、成功版本及 processed_at，並寫入 last_error。重新解析會產生新的公告內部 ID，外部追蹤使用郵件 ID／source_index／fingerprint。

主要資料表欄位：

| 表 | 欄位群組 |
| --- | --- |
| emails | id、gmail_message_id、subject、sender、received_at、html_body、text_body |
| emails 狀態 | status、processed_at、parser_version、last_error、warnings |
| announcements 來源 | id、email_id、source_index、source_fingerprint、announcement_date、department、source_category、title、original_text、original_html、url |
| announcements 日期 | event_date、deadline、date_evidence、date_inferred、created_at、updated_at |
| announcements 分析預留 | category、summary、keywords、requires_action、scraped_text、analysis_status、analysis_version |

僅當 source_category 完全符合既定分類時複製到 category；其他保留 NULL。公告日期、摘要與行動需求不猜測；分析狀態先為 pending。本階段不呼叫 AI 或爬蟲。
重解析失敗但仍有舊成功資料的郵件維持 processed，因此不計入 failed_emails；本次失敗會出現在 failed／errors。
這是本專案第一版 schema；`create_all` 用於建表，不會自動遷移未來的欄位變更。

新增實作位於 `app/models/`、`app/database/database.py`、`app/services/sync_service.py`。
`tests/test_database.py` 和 `tests/test_sync.py` 使用暫存 SQLite、合成郵件和模擬 Gmail，涵蓋交易回滾、重試、版本更新、重啟及並行寫入，不連線真實 Gmail。

## 7. 第③階段：本機 Dashboard

在專案根目錄開啟 PowerShell，執行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

開啟 [Dashboard](http://127.0.0.1:8000)，停止伺服器按 Ctrl+C。
這是單人本機工具，使用一個 Uvicorn worker。請維持 127.0.0.1 綁定；尚未設計公開部署的使用者登入與多帳號隔離。

1. 首頁顯示今日收到、需要處理、即將截止及已整理總數。今日依台北收件日計算；即將截止指今天到第 6 天結束，排除過期與未知日期。
2. 左側切換全部、今日、即將截止、需要處理、AI／科技、就業／實習；可搭配分類與主旨／單位搜尋，每頁 20 筆。
3. 尚未分析的行動需求顯示「尚未判定」，不自動當成 false。分類使用已儲存 category；未分類公告也用原始性質與主旨關鍵字比對，這只是篩選，不改寫資料或呼叫 AI。
4. 點擊公告主旨查看原文與日期證據。原文只以純文字顯示，HTTP(S) 公告連結可另開分頁，不直接執行郵件 HTML。
5. 選擇最近 5／20／50／100 封並按「同步 Gmail」。同步中會停用按鈕，完成後更新統計與列表，顯示處理、略過、失敗數。單封失敗仍保留成功資料；同一伺服器的第二個同步請求回傳 409。

| API | 用途 |
| --- | --- |
| `GET /api/summary` | 台北今日統計、7 天期限、未知行動需求及最近成功處理時間 |
| `GET /api/announcements` | view、category、q、page、page_size 篩選與分頁 |
| `GET /api/announcements/{id}` | 單筆公告原文及日期證據 |
| `POST /api/gmail/sync` | JSON `{"limit":5}`；本機前端附帶 `X-Requested-With: NKUST-Dashboard` |

`view` 支援 all、today、deadline、action、jobs、tech。分類與搜尋條件會與 view 取交集；切換 view 不會清除已選分類與搜尋文字。
「最近成功處理」取自郵件的 processed_at；全部略過的同步不會更新這個時間。
同步 request 期間會持續執行；前端關閉或重新整理不代表伺服器已取消，重複請求會被同步鎖拒絕。
頁面及 API 不使用外部 CDN，郵件不會因顯示在 Dashboard 而傳送至第三方。

新增檔案：`app/main.py`、`app/api/announcements.py`、`app/api/gmail.py`、`app/templates/index.html`、`app/static/css/dashboard.css`、`app/static/js/dashboard.js`、`tests/test_api.py`。
API 測試涵蓋台北日界、截止日期邊界、分頁、分類、原文、輸入驗證、重複同步、鎖定與錯誤復原。瀏覽器檢查涵蓋真實資料、原文對話框、分類与同步操作。

## 第④階段：iAI 公告分析

1. 登入高科大 iAI，在 API Key 頁取得自己的金鑰，只寫入本機 `.env` 的 `AI_API_KEY`，不要提交 Git 或貼到對話中。
2. `AI_PROVIDER=iai`，`AI_BASE_URL=https://www.iai.nkust.edu.tw/aihub/v1`。執行 `.venv\Scripts\python.exe -m app.cli ai-models` 查詢正式模型 ID，這一步不傳送郵件。
3. 設定 `AI_MODEL=Furen-std`。此模型已驗證支援 Chat Completions 與 `response_format: {"type":"json_object"}`；其他模型尚未實測，不會自動切換模型。
4. 執行 `.venv\Scripts\python.exe -m app.cli ai-check`，只傳送內建虛構公告，檢查格式與民國日期。修改 `.env` 後，重新啟動 Dashboard 服務。
5. Dashboard 按「分析 5 則」才會傳送最多 5 則公告文字給 iAI。原文詳情可查看摘要、分類、關鍵字、行動判斷與逐字引用的依據。失敗項目需按「重試失敗項目」。

瀏覽頁面、同步 Gmail 都不會自動觸發 AI。AI 不會收到 OAuth token、Gmail 寄件地址或整封 HTML；分析資料包含寄件單位、原始性質、主旨、公告原文、收件年份與規則辨識的日期。公告原文若含個資，這些文字也會隨分析請求傳送。iAI 是外部服務，不能僅憑校方網址推定所有模型只在校內處理資料；請以校方及所選模型的說明為準。

分析格式採嚴格 JSON schema。日期與行動依據必須出現在原文，無法支持的判斷轉為未知並留下提醒；這是格式與文字依據檢查，不保證 AI 摘要或語意判斷完全正確。既有日期解析器結果優先，AI 的空值不會清除日期。`requires_action=true` 代表公告含可採取的行動，不代表使用者符合資格或必須參加。

新增 `announcement_analyses` 表保存模型、版本、輸入摘要雜湊、結果、錯誤碼與提醒，無須重建既有資料表。原文欄位不改寫；同一模型與分析版本已完成的項目會略過，換模型或版本可重新分析。分析期間若原始資料改變，舊結果會被略過。失敗時保留既有摘要。重新解析郵件仍會原子替換該封公告，並透過外鍵清除其舊分析紀錄。

API：`GET /api/ai/status`（本機設定與進度，不返回金鑰）；`POST /api/ai/analyze`（`{"limit":5,"retry_failed":false}`，最多 20 則，須有 Dashboard 自訂標頭與同來源）。UI 的分析與同步共用鎖；請以單一服務程序啟動，不要同時開多個服務對同一資料庫分析，以免重複消耗額度。關閉網頁不會取消已發出的請求。

Provider 介面位於 `app/providers/base.py`，iAI 實作位於 `app/providers/iai.py`，輸出契約位於 `app/schemas/analysis.py`，驗證與批次儲存分別位於 `app/services/ai_analyzer.py`、`app/services/analysis_service.py`。API 與頁面不依賴廠商 SDK。第④階段不包含 Scrapling 或外部網站擷取。

## 第⑤階段：公告網頁補充內容

1. 點開公告，在詳情底部按「擷取網頁」。只讀取該筆公告儲存的 URL，不會追蹤正文內的其他連結。
2. 成功後會顯示網頁正文與來源；與郵件原文分開保存。按「分析這則公告」才會將兩者送往 iAI，更新該則摘要與判斷。
3. 若按「重新擷取網頁」，內容變更時標記為待分析，舊摘要仍保留並明確標示；舊網頁衍生日期會清除，郵件解析得到的日期保留。擷取失敗則保留先前成功內容。

`SCRAPE_ALLOWED_HOSTS=officemail.nkust.edu.tw` 是預設精確主機清單，可在本機 `.env` 以逗號分隔新增經確認的公告主機。只接受 HTTPS、443 埠與公開 IP，拒絕帶帳密的網址及私有位址。每次轉址都驗證，最多 3 次；原始 URL 不被改寫，最終 URL 記錄在 `announcement_scrapes` 表。一般 HTTP 擷取使用 Scrapling 0.4.15，20 秒逾時、最多兩次嘗試、固定 User-Agent、憑證驗證與下載大小限制。為固定 DNS 至已檢查的公開 IP，傳輸適配使用 Scrapling 底層 curl session 設定，故鎖定套件版本並以測試覆蓋；升級須重新驗證。

正文上限 12,000 字，送給 AI 的標題與合併正文上限仍為 16,000 字；超限會明確失敗，不偷偷截斷。支援高科公告 MailView 版型與常見 main/article 正文區塊；登入頁、未知版型、PDF、附件、只靠 JavaScript 載入的內容不視為成功。此階段不使用瀏覽器登入、自動填表、反爬繞過或網站遞迴擷取，也不修改 Gmail。

`POST /api/announcements/{id}/scrape` 接受 `{"refresh":false}`，預設重用成功快取；前端重新擷取會使用 true。需要 Dashboard 自訂標頭及同來源，與同步/AI 共用作業鎖。`GET /api/announcements/{id}` 包含 web 來源、擷取時間、正文及錯誤。`POST /api/ai/analyze` 可指定 `announcement_id` 分析單則。網頁內容也視為不可信輸入；日期和行動依據可逐字對照郵件或網頁，但仍需人工核對摘要。

主要新增：`services/scraper.py`、`services/scrape_service.py`、`models/scrape.py`、`api/scrape.py`，以及擷取、儲存、API 的測試與去識別化 HTML fixture。真實網頁樣本只存於被 Git 忽略的 `data/samples/private/`。使用前安裝更新後的 requirements，重新啟動本機服务即可自動新增紀錄表，不需清空資料庫。
