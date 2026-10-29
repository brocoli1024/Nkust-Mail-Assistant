# 校園通知待辦助手第一階段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 使用者於 2026-10-29 選擇由目前代理在本對話逐項執行，第一階段已完成。

**Goal:** 學生免登入閱讀、搜尋及分類公開公告，無 Gmail／AI 金鑰亦可體驗明確標示的合成資料。

**Architecture:** 沿用 `app.web:app`、FastAPI／Jinja 與公開獨立資料表。新增純記憶體示範資料與唯讀路由，公開三頁共用來源狀態模板，維持私人路由、同步服務與 PWA 快取邊界。

**Tech Stack:** Python、FastAPI、Jinja2、SQLAlchemy、pytest、原生 JavaScript／Node，沿用既有依賴。

**Spec:** `docs/superpowers/specs/2026-10-29-campus-action-phase1-design.md`（使用者已核准）。

## Global Constraints

- 第一階段僅完成公開閱讀與合成示範，不提前實作行動卡或待辦。
- 不預期需要 migration、新套件或新服務；若出現需求，先修訂規格。
- 不推送部署分支、不觸發正式部署、不執行正式 migration、不讀寫正式資料庫、不修改 OAuth、不啟用付費或排程服務。
- 保留 Jinja 自動跳脫、來源 URL 驗證、既有 CSP 及 no-store。PWA 不新增公告、私人內容或示範資料離線快取。
- 繁中介面；320px 及 390px 不水平溢出。保留所有既有未提交修改；不得複製 `.env`、憑證或私人資料至測試／新工作區。

## Review Focus

1. 有效／偽造 Cookie 均不得讓公開與示範頁讀取 Session 或私人資料（Task 1、3）。
2. 篩選零結果與整個來源零資料必須區分，翻頁與變更篩選不遺失條件（Task 2、4）。
3. 無成功更新、partial／failed 維護及未知日期不得顯示假成功或使用當天日期（Task 1、2）。
4. 瀏覽器上一頁／無 JavaScript 時，表單仍可操作且不殘留載入狀態（Task 4）。
5. 不合法路徑、惡意文字與資料庫失敗需保留狀態碼、安全跳脫及私人 API 既有契約（Task 3、4）。

## 檔案與責任

| 區域 | 檔案與責任 |
| --- | --- |
| 公開頁 | `app/api/public_announcements.py`；三個 `public_*.html`；新增 `public_source_status.html`：共用來源狀態、區分空白原因 |
| 合成示範 | 新增 `app/services/demo_announcements.py`、`app/api/demo.py`、`demo_announcements.html`、`demo_announcement_detail.html`、`demo_notice.html`：固定資料、搜尋／分類、隔離提示 |
| 共用介面 | `site_header.html`、`login.html`、`account.css`、`announcement-filters.js`：入口、手機、載入狀態 |
| 掛載／錯誤 | `app/web.py`；新增 `public_error.html`：路徑限定 HTML 錯誤，不改私人 API |
| 驗證／文件 | 既有公開、隔離、PWA 測試；新增 `test_demo_pages.py`；README、公開手冊及階段驗證紀錄 |

## 執行前條件與測試指令

先讀 `using-git-worktrees` 決定隔離方式，保留目前工作區既有修改；不得 reset、stash 或將它們混入功能提交。以已提交 HEAD 建立功能工作區時，既有未提交發布紀錄只作歷史證據，不複製正式設定。後續所有命令明確指定選定工作區。

PowerShell 下的 `$phasePython` 指向目前已存在的 `.venv/Scripts/python.exe` 絕對路徑（若使用新工作區，仍可使用原工作區執行檔，不安裝新依賴）。測試暫存位置使用執行工作區內 `data/audit-cache/phase1-<唯一執行識別碼>`，每輪建立全新路徑；pytest `--basetemp` 會清除指定目錄，禁止指向既存資料或工作區根目錄。

共用測試前綴：`& $phasePython -m pytest -p no:cacheprovider --basetemp=<本輪新測試目錄> --tb=short`。不得讓資料庫 fixture 退回環境中的正式 `DATABASE_URL`。保留測試退出碼與計數；執行逾 60 秒仍無進度時先輸出狀態，再定位停滯，不以中止視為通過。

### Task 1：恢復可信基線（約 15–30 分鐘，若需修環境則另記）

**Files:** 先只讀 `tests/test_sessions.py`、`tests/test_auth.py`、`tests/test_multi_user_database.py`、`alembic/env.py`；必要的 fixture 修改限已證明的原因。新增 `docs/campus-action-phase1-validation-2026-10-29.md` 記錄命令與結果。

**Interfaces:** 消費 `web`／`database` fixture 的獨立 SQLite 與 FakeGoogle；產出可重現的測試指令，不更動應用資料庫契約。

- [x] 先以 `--collect-only -q` 確認收集，再單跑 `tests/test_public_sync.py::test_sync_repeat_update_and_source_failure -vv -s`；使用新 basetemp，判斷建立目錄、migration 或 TestClient 哪一步停住。
- [x] 若仍失敗，使用 `systematic-debugging`，最小重現後才處理。只有 fixture 本身有錯才改測試程式；不為 sandbox 限制改產品安全邊界。回歸案例必須先失敗、修復後通過。
- [x] 跑 `tests/test_public_pages.py tests/test_public_sync.py tests/test_date_parser.py tests/test_user_isolation.py`。期望退出 0；記錄實際 passed／skipped／warning，遇失敗不帶著未解決基線開始產品改動。
- [x] 記錄失敗原因、修正方式與測試範圍；只提交本 task 的紀錄及必要 fixture 修正，不包含原有 readiness 修改。

### Task 2：公開入口與來源資訊（約 30–45 分鐘）

**Files:** 修改 `app/api/public_announcements.py`、`public_home.html`、`public_announcements.html`、`public_announcement_detail.html`；新增 `public_source_status.html`；修改 `tests/test_public_pages.py`。

**Interfaces:** 沿用 `status_data(session) -> dict`；新增清單 context `source_total: int` 表示未套篩選的指定來源總數。`detail()` 在同一交易取得 `item` 與 status；不得讀私人表。共用模板消費既有 `last_success/oldest/history_status/history_completed/last_run_status/source_url`。

- [x] 新增失敗測試 `test_source_status_is_visible_on_all_public_pages`：三頁 HTML 均在未折疊區顯示來源、固定台北時間與範圍；無成功紀錄顯示「尚無成功更新紀錄」；parametrize partial／failed，驗證失敗提示、資料仍在、時間未被替換。
- [x] 新增 `test_empty_source_differs_from_empty_search`：空庫顯示「目前尚無收錄資料」及 `/demo`；seed 後無結果顯示「沒有符合篩選的公告」及清除連結。執行上述新測試，確認因現有行為不足而失敗。
- [x] 最小修改 context 與模板；首頁加入示範入口及「選用：我的 Gmail 公告」，共用來源區不捏造更新頻率；無摘要、非法 URL 繼續沿用既有安全處理。
- [x] 跑 `tests/test_public_pages.py tests/test_public_sync.py tests/test_announcements_auth.py`，期望退出 0。確認既有有效／偽造 Cookie 隔離測試與同來源搜尋分頁仍通過。
- [x] 僅提交本 task 檔案，訊息 `feat: clarify public announcement entry and source status`。

### Task 3：不需個人整合的合成示範（約 35–50 分鐘）

**Files:** 新增 demo service、router、三個 demo 模板及 `tests/test_demo_pages.py`；修改 `app/web.py` 掛載、`site_header.html`、`login.html` 加入入口。

**Interfaces:** `DemoAnnouncement` 為 frozen dataclass，欄位 `id: str, title: str, excerpt: str, category: str, published: str | None`。常數 tuple `DEMO_ANNOUNCEMENTS` 固定三筆；`list_demo_announcements(q: str = '', category: str = '') -> tuple[DemoAnnouncement, ...]`、`get_demo_announcement(demo_id: str) -> DemoAnnouncement | None` 均純函式。ID 為 `demo-scholarship`／`demo-event`／`demo-notice`，分類分別為獎學金／活動／行政通知；前兩筆日期固定 `2026-09-01`／`2026-09-02`，第三筆無日期及摘要。

- [x] 新增測試：`test_demo_filter_and_detail` 驗證三筆、搜尋「獎學金」、分類組合、清除條件、未知日期與摘要；`test_demo_never_reads_integrations` 在服務啟動後將 database.transaction、sessions.resolve、sync_service.sync_gmail_for_user設為呼叫即失敗，匿名／有效 Cookie／偽造 Cookie 讀取 demo 清單及詳情仍 200。外部 HTTP 傳輸也設為呼叫即失敗。
- [x] 加入 `test_demo_labels_unknown_ids_and_escaping`：每頁包含「合成示範資料，非高科大真實公告，請勿據此報名或申請」、固定示範日期，未知 ID 404、未知分類與超過 200 字搜尋 422；query 中 `<script>` 安全跳脫。頁面不得含 `PRIVATE-MARKER`、真實收錄數／最後成功更新、報名或待辦操作；DB 列數不變。執行新檔，確認缺少路由而失敗。
- [x] 實作上述純資料介面與 GET `/demo?q=&category=`、`/demo/announcements/{demo_id}`，沿用 CATEGORIES 驗證與 escaped Jinja。示範列表僅三筆不增加分頁；分類與搜尋不呼叫資料庫。只在 `session_enabled` 多人 app 中掛載。
- [x] 導覽與登入頁明示 Gmail 為選用唯讀整合、Google 測試名單限制，提供公開與示範返回入口。demo 共用提示模板，無捏造的官方原文；首頁連結可前往實際示範。
- [x] 跑 `tests/test_demo_pages.py tests/test_public_pages.py tests/test_sessions.py tests/test_pwa.py`，期望退出 0；確認 CSP／no-store 與 Service Worker 不快取 demo。僅提交本 task 檔案，訊息 `feat: add isolated synthetic announcement demo`。

### Task 4：表單、手機與公開頁錯誤（約 35–50 分鐘）

**Files:** 修改 `announcement-filters.js`、`account.css`、公開／示範表單模板、`app/web.py`；新增 `public_error.html`；擴充 `tests/announcement_filter_check.cjs`、`test_public_pages.py`、`test_demo_pages.py`。

**Interfaces:** 表單保留 `id="announcement-filters"`；新增狀態元素 `id="filter-status" role="status" aria-live="polite"`。選單 change 仍用 requestSubmit；submit 顯示載入及 form aria-busy；window pageshow 清除兩者。不禁用表單欄位以免 GET 遺失值。無 form 時腳本安全結束。

- [x] 擴充 Node 行為測試：兩個 select 各提交一次、Enter submit 設 busy 與狀態、pageshow 清除、缺少表單不 throw；斷言未將欄位 disabled。Python 驗證 GET 表單不含舊 page 值、下一頁保留篩選及 noscript 可提交；先執行確認新斷言失敗。
- [x] 新增公開頁參數錯誤測試（q 過長、category 未知、page=0、未知詳情）及資料庫讀取失敗測試，期待繁中 HTML、正確 422／404／503 與安全返回連結；斷言錯誤文字不含 SQL／例外私人標記。另測 `/api/me` 匿名仍 JSON 401、私人參數錯誤維持既有 JSON 契約。
- [x] 實作狀態腳本及共用 HTML 錯誤頁。`web.py` 僅對 GET `/`、`/public/announcements` 與其詳情、`/demo` 與其詳情採用此回應；依現有 exception handler 擴充分支，其他路徑沿用原契約。錯誤頁不讀 DB／Session，重試連結不用任意外部輸入。
- [x] CSS 沿用配色，補表單堆疊、長標題換行、focus-visible、操作區至少 44px；在 320px／390px 實際瀏覽器確認無溢出、Tab 可到搜尋／分類／來源、返回恢復狀態。若無可用 UI 工具，明列未驗證，不以 HTML 斷言替代視覺驗收。使用介面技能前讀取適用指引。
- [x] 跑 Node filter check 與受影響 pytest，期望退出 0；提交 `fix: improve public page feedback and mobile usability`。

### Task 5：文件、完整驗收與第一階段交付（約 20–35 分鐘）

**Files:** 修改 `README.md`、`docs/public-announcements.md`、本階段 validation 文件；必要時更新本計畫 checkbox。

**Interfaces:** 消費前四 task 的路由與測試結果，產出可以獨立閱讀的啟動、示範、限制與驗收紀錄。無新產品介面。

- [x] README 與公開手冊列出免登入／demo／選用 Gmail，分開單人與多人啟動條件。部署狀態寫「10/28 工作區發布紀錄記載曾部署；本次新增功能未部署」，不把未提交記錄當成已驗證今天正式狀態；不寫固定真實公告數。
- [x] 跑完整 pytest（獨立 SQLite，未提供專用 PostgreSQL URL 則明列相關 skipped）、`node tests/announcement_filter_check.cjs`、`node tests/pwa_worker_check.cjs` 及 `git diff --check`。Node 若不在 PATH，先找已安裝 runtime，不安裝服務。記錄命令、退出碼、計數、警告及限制。
- [x] 依 `requesting-code-review` 進行最終檢查；若使用 reviewer 子代理，必須符合使用者選定的執行方式與技能要求。依 `verification-before-completion` 以實際輸出確認完成，不修無關問題。
- [x] 僅提交本階段文件／程式／測試，檢查 diff 不含憑證及既有修改；禁止 push、migration 正式庫或觸發部署。
- [x] 回報第一階段修改、驗證、限制及第二階段建議；第二階段進入各自設計流程，本計畫不授權直接實作後續階段。

## 自我審閱與執行選項

規格對應：公開閱讀及來源透明度 → Task 2；示範及 Gmail 選用 → Task 3；手機／空白／載入／錯誤 → Task 2、4；隔離及部署界線 → 全域限制、Task 1、3、5；後續銜接 → 規格第 8 節，第一階段不實作。

建議 Native：目前代理在本對話依序執行五項 task，完成後按 review 技能檢查，避免每項重建上下文。估計 2–3.5 小時；測試環境或 UI 工具限制會影響時間，會明列實測結果。另一選項為子代理逐任務實作與審查，隔離審查較多、上下文成本較高。兩者均不另建使用者聊天，也不部署。

狀態：計畫經使用者核准，第一階段已實作與驗證，獨立審查無阻擋缺陷；限制與延期項目見第一階段驗證紀錄。
