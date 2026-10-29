# 公告行動資訊卡 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 使用者已選擇在本對話 inline 實作；不另派實作者，完成後做一次新上下文整體審查。

**Goal:** 在公開、私人及合成示範詳情顯示可追溯的行動資訊，提供不覆寫原解析的個人修正與歷史。

**Architecture:** 純來源轉接與卡片規則建立共同 DTO；伺服器以現有 Jinja 顯示卡片。公開修正使用原生 IndexedDB 交易，私人修正使用 owner-bound SQL 快照與追加紀錄；兩者都用基準 hash 與預期 revision 防止誤套及覆寫。

**Tech Stack:** 既有 Python／FastAPI／Pydantic／Jinja／SQLAlchemy／Alembic、原生 JavaScript／IndexedDB、pytest／Node；不增加套件或外部服務。

**Spec:** `docs/superpowers/specs/2026-10-29-campus-action-phase2-design.md`，使用者已核准。計畫基準為 `cee8373`；第一階段產品基準 `818e0e9`。

## Global Constraints

- 本階段不呼叫新 AI、不掛載單人 API、不擷取新全文。本階段不實作待辦或行事曆。
- 新增 migration 僅編寫及在獨立測試庫執行；不改正式庫、不部署、不推送部署分支、不修改 OAuth、不新增付費或排程服務。
- 所有 GET 讀取不觸發 Gmail、AI、全文擷取、資料遷移或修正寫入。
- 私人原文、快照與修正不寫入 IndexedDB、localStorage、sessionStorage 或 Service Worker 快取。
- 介面繁中，沿用配色；320／390px、鍵盤與錯誤驗收。保留原工作區既有未提交修改及所有來源／原解析，不複製 `.env`／憑證。

## Review Focus

1. 相同日期文字出現於發布、截止及活動不同上下文，或含推定年份／範圍時，不可因單一關鍵詞升級為確定值（Task 1）。
2. 公告重建可能重用數字 ID 或改變索引，舊修正不得丟失或套到另一則公告（Task 2、3）。
3. 同帳號同步、刪除與兩個修正寫入同時發生時，不得死鎖、跨 owner 或靜默覆寫（Task 2、3）。
4. 瀏覽器 put 成功但交易後續 abort、儲存額度不足或多分頁競爭時，不得顯示已保存（Task 4）。
5. 既有 AI 版本／輸出損壞、JavaScript 不可用、讀取歷史失敗時，仍可看來源，且不以空白狀態掩蓋失敗（Task 1、3、4）。

## 檔案責任與共同契約

| 區域 | 檔案 |
| --- | --- |
| 卡片與證據 | 新增 `app/schemas/action_cards.py`、`app/services/action_cards.py`、`app/services/action_card_rules.py`；既有 `date_parser.py` 維持契約 |
| 私人保存 | 新增 `app/models/action_cards.py`、`app/services/action_card_corrections.py`、`alembic/versions/0007_action_card_corrections.py`；修改 `alembic/env.py`、`app/database/schema.py` |
| 路由與模板 | 新增 `app/api/action_card_corrections.py`、`action_card.html`、`action_card_editor.html`、`action_card_history.html`、`action_card_error.html`；修改三種詳情路由／模板、`app/web.py` |
| 裝置與互動 | 新增 `app/static/web/action-card-store.js`、`action-card.js`；修改 `account.css`、示範說明與隱私頁 |
| 驗證與文件 | 新增 `tests/test_action_cards.py`、`test_action_card_corrections.py`、`test_action_card_pages.py`、`test_action_card_postgresql.py`、`action_card_store_check.cjs`、`tests/browser/action_card_store.html`、階段驗證紀錄；擴充既有相關測試 |

### DTO（Task 1 定義，後續任務只使用）

`SourceSegment(kind: 'title'|'excerpt'|'original', text: str)` 與 `SourceDocument(kind: 'public'|'private'|'demo', source_ref: str, title: str, segments: tuple[SourceSegment,...], url: str|None, anchor: datetime|None, metadata: dict)` 為 frozen Pydantic 模型。metadata 只接受來源轉接白名單，不接受客戶端傳入的私人來源快照。

`Evidence(segment, quote, start, end, role, year_inferred)` 的座標對應指定段落原文；`CardField(value: str|None, state: supported|pending|user_confirmed|stale, evidence: tuple[Evidence,...], origin: str, warnings: tuple[str,...])`。

`ActionCard` 包含 source、source_hash、baseline_hash、parser_version、`fields`（summary/action/audience/materials/deadline/event_date 六鍵）、requires_action（bool|None）、deadline_kind（registration/application/submission/unknown）、candidates、legacy、ai_references、warnings。時間狀態另記 `time_status=unparsed|not_provided|unknown`，不得由它直接匯出 ICS。

`CorrectionPatch` 只接受六鍵的欄位指令 `{mode: inherit|value|pending, value: str|None, quote: str|None, confirmed: bool}`，另有 `action_decision=yes|no|unknown` 及 `deadline_kind`。只有 action／deadline 使用相應附加欄；其他 owner、url、原始快照等額外欄位一律拒絕。`mode=value` 的日期須有效且 confirmed=true，仍標 user_confirmed。inherit、pending 與空字串不混用。

摘要 160 字；行動／對象／材料各 1,200 字；引用各 2,000 字。所有 schema 禁止未知欄位，不截斷後保存。`display_context(card, *, now: datetime) -> dict` 負責台北今天與過期提示，這些動態值不納入 baseline hash，避免每天令修正失效。

### 執行環境

執行時先讀 `executing-plans`、`using-git-worktrees`、`test-driven-development`。已掛載工作區 `C:/Users/leogo/.codex/worktrees/campus-action-phase1/Nkust-Mail-Assistant` 為乾淨 detached worktree，沿用它，不再新建工作區。權限不足時走標準 escalation，不繞過 sandbox；不改原目錄的既有修改。

既有 Python 在 `C:/Users/leogo/OneDrive/文件/ChatGPT/Nkust-Mail-Assistant/.venv/Scripts/python.exe`，以下以 `$phasePython` 指向此絕對路徑。每輪 basetemp 使用工作區內全新 `data/audit-cache/phase2-<識別碼>`，先建立父目錄；禁止重用含有保留資料的目錄。第一階段發現 sandbox 內 Windows socketpair 會阻塞 TestClient，必要時請求審核後在 sandbox 外執行同一組合成測試，不為此修改產品程式。

共用測試前綴：`& $phasePython -m pytest -p no:cacheprovider --basetemp=<本輪新目錄> --tb=short -o faulthandler_timeout=30`。每次讀退出碼及實際計數；完整回歸前的基線應為第一階段記錄的 439 passed、37 PostgreSQL skipped，實際不同先釐清。PostgreSQL 只接受 `NKUST_TEST_POSTGRES_URL`，不回退 `DATABASE_URL`。

## Task 1：有原文依據的卡片核心（約 60–90 分鐘）

**Files:** 新增 schemas／services／rules 與 `tests/test_action_cards.py`；新增 `docs/campus-action-phase2-validation-2026-10-29.md` 記錄基線與每次 RED／GREEN。

**Interfaces:** 產出上述 DTO、`build_action_card(source: SourceDocument, *, legacy: dict|None=None, ai_references: tuple[dict,...]=()) -> ActionCard`、`apply_patch(card: ActionCard, patch: CorrectionPatch) -> ActionCard`、`display_context`。在 action_cards.py 提供 `public_source(row) -> SourceDocument`、`private_source(row, received_at, *, email_parser_version: str|None) -> SourceDocument`、`demo_source(item) -> SourceDocument`；它們只讀傳入資料，不查 DB 或網路。規則輔助集中在 action_card_rules.py。

代表性斷言（tests/test_action_cards.py；匯入上述 Task 1 介面）：

```python
source = SourceDocument(kind='public', source_ref='public:test', title='合成公告',
    segments=(SourceSegment(kind='excerpt', text='報名截止：115年10月08日；活動日期：115年10月21日'),),
    url=None, anchor=None, metadata={})
card = build_action_card(source)
assert card.fields['deadline'].value == '2026-10-08'
assert card.fields['event_date'].value == '2026-10-21'
assert card.fields['deadline'].state == 'supported'
```

- [ ] 先跑現有 `test_public_pages/test_demo_pages/test_date_parser/test_user_isolation` 基線，期望 exit 0，記錄實際計數。
- [ ] 寫 `test_card_dates_require_roles_and_explicit_year`：完整「115年10月08日報名截止、115年10月21日舉辦活動」得到分離的 supported 日期；省略年份時公開 pending、私人可保留推定候選但仍 pending；發布／收件日期不成活動日。
- [ ] 加入參數化日期案例：非法 2/30、明年／跨年、兩個不同截止、日期範圍、同日期文字不同角色、標題與原文重複、不含時間／有時間但未解析；驗證不自行取最早或最晚，每段 evidence 切片等於 quote，legacy 原值仍可查。
- [ ] 寫 `test_actions_audience_and_materials_need_source_evidence`：「無須報名，但請繳交報告」只辨識繳交要求；僅分類／錄取名單不判為須行動；缺對象／材料 pending。原文標示對象可擷取，但 DTO 沒有 is_eligible。加台北跨日 `display_context` 與 hash 不隨 now 改變案例。
- [ ] 寫 AI／修正案例：缺 hash 對應、損壞 JSON、未知版本、失敗分析、虛構引文、只有 AI 日期不得升級；保留可驗證引文及版本警告。修正日期確認、pending／inherit、160／1200／2000 邊界與未知欄拒絕，apply_patch 不改原 card。執行新測試，預期缺模組／函式而失敗。
- [ ] 實作最小規則：逐段沿用 parse_dates 作候選，要求局部明確角色，排除發布／收件／更新上下文及歧義。對象材料僅取明示且可界定的段落；行動檢查否定與指示語句。來源摘要／節錄標明來源，摘要預覽截短有標示且原文完整可展開。AI 只做無外呼的既有資料驗證。
- [ ] source_ref：公開為規範化 `[source_key, canonical_url]`，私人為 email_id/source_index/source_fingerprint 的來源身份（owner 另由服務綁定），demo 為 demo:id。source hash 用明確白名單與規範化 UTC 時間；baseline hash 包含解析版本、legacy／採用 AI 的靜態內容，不含讀取或過期提示時間。私人來源 adapter 不使用公告 ID 作身份。
- [ ] 公開／demo 的 anchor 固定 None，不以 published_at 補年；私人 SQLite naive received_at 依既有合約視為 UTC，規範化後轉台北供候選推年，推年結果仍 pending。AI 參考由 owner-scoped completed 紀錄的 created_at/id 排序選取並驗證，未知版本留參考區，不呼叫單人 AnalysisService。
- [ ] 跑新測試＋`tests/test_date_parser.py tests/test_ai_analyzer.py tests/test_announcement_parser.py`，期望 exit 0。僅提交本 task 檔案，訊息 `feat: build evidence-backed announcement action cards`。

## Task 2：私人不可覆寫快照與修正保存（約 60–90 分鐘）

**Files:** 新增 `app/models/action_cards.py`、`app/services/action_card_corrections.py`、migration `0007`、`tests/test_action_card_corrections.py`、`tests/test_action_card_postgresql.py`；修改 `alembic/env.py`、`app/database/schema.py`、必要的既有 schema 版本斷言與 PostgreSQL 離線 downgrade 測試。

**Interfaces:** 兩個模型為 `PrivateActionSnapshot`／`PrivateActionRevision`，欄位及 owner 複合 FK／唯一約束依規格；快照增加 `revision_count: int`，預設 0。`PrivateCardView(item: dict, base: ActionCard, effective: ActionCard, patch: CorrectionPatch|None, revision: int, history: list[dict], stale: bool)` 為 detached DTO。

服務介面：`load_private_view(database, user: CurrentUser, announcement_id: int) -> PrivateCardView`；`save_private_correction(database, user, announcement_id, *, expected_revision: int, baseline_hash: str, operation: save|reset, patch: CorrectionPatch|None) -> int` 回傳新 revision；`load_private_history(database, user, snapshot_id: int, *, page_number: int=1) -> dict`。錯誤型別 `CorrectionNotFound`、`CorrectionConflict`、`CorrectionUnavailable` 分別對應 404、409、503；不在例外內保存 SQL／郵件／供應商原始錯誤。

代表性 migration 斷言（使用既有 database fixture、sqlalchemy.inspect）：

```python
db, config = database
assert {'private_action_snapshots', 'private_action_revisions'} <= set(inspect(db.engine).get_table_names())
```

保存案例需另核對原快照等於儲存前 base.model_dump(mode='json')、revision 依序為 1／2／3，並逐筆比對 owner，不以表存在取代服務驗證。

- [ ] 寫 `test_0007_preserves_existing_data_and_owner_fks`：獨立庫停在 0006，種私人／公開資料，升級 0007、重跑、比對既有內容及 metadata；跨 owner Email／snapshot FK 被拒，revision 唯一且正數。合成庫降回 0006 只移除新表，再升級；新修正被刪的事實須明列，不能當正式無損回復。
- [ ] 寫保存案例：GET 不建資料，首次 save 建一個原快照及 revision1；第二次及 reset 追加，原文／original_card 不變。讀寫／歷史皆檢查 User.google_user_id、Announcement.user_id、Email.user_id；錯 owner 與已刪重建的 CurrentUser 不能存取。
- [ ] 寫 `test_reparse_preserves_history_without_applying_to_reused_id`：保存後用現有 repository 強制重新解析，原快照仍在；換來源文字、索引或指紋使舊修正 stale。不得假設 SQLite 新 ID 一定不同。現在同封郵件詳情能找到舊快照，但不自動套用。
- [ ] 寫版本／併發案例：同 expected_revision 的兩個 save 至多一個成功；其他回 conflict 或可重試 unavailable，不得假成功。與同步／刪除並行時不得留孤兒或跨 owner。刪本人帳號 CASCADE 新資料，但別人及公開資料不變。PostgreSQL 版重用同一服務合約，未設定專用 URL 則 skip。
- [ ] 執行上述新測試，預期缺表／函式失敗，再實作模型、migration 及服務。只新增表，REQUIRED_REVISION 更新 0007，註冊新 metadata；不執行 CLI 對現有設定庫遷移。
- [ ] 保存交易先鎖定／驗證 User 身分，再讀本人公告及 Email，重建當前 base 並比較 hash。建立唯一快照、用 revision_count 的 compare-and-update 後追加 revision，同交易提交；遇 CAS 失敗回 conflict，SQLite 鎖忙回 unavailable，不無限重試。鎖序沿用 User 優先，不取得會呼叫 Gmail 的新服務。
- [ ] 快照不對公告 ID 建 FK，保留原 source_text、metadata、original_card。load 只套用同來源身份與 baseline 的最新完整 overrides；其他是歷史。讀取歷史最多每頁 20 筆、依 created_at/id 降冪，不因一次 reset 丟掉舊版本。
- [ ] editor 由目前完整 patch 預填模式與值，不從空白表單覆蓋未改動欄位；加入「只改活動日期仍保留先前材料修正」案例。私人 revision 以 snapshot 為範圍，新 baseline 從 0 開始；裝置 revision 則以 source_ref 紀錄為範圍，新增 baseline 仍沿用整筆紀錄的版本序列，UI 先 read 再使用預期值。
- [ ] 跑新測試＋`tests/test_multi_user_database.py tests/test_public_database.py tests/test_account_controls.py tests/test_postgresql_readiness.py`，期望 exit 0（PG 實機另列 skip）。提交 `feat: persist owner-scoped action card revisions`。

## Task 3：三種詳情行動卡與私人表單（約 60–90 分鐘）

**Files:** 新增 correction API 與四個共用模板、`tests/test_action_card_pages.py`；修改 `app/api/public_announcements.py`、`user_announcements.py`、`demo.py`、三種詳情模板、`app/web.py`、`account.css`；擴充公開／示範／帳號／PWA 測試。

**Interfaces:** 公開／demo detail 傳 `card`、`card_context=display_context(...)`、`scope=public|demo`，私人由 load_private_view 得到 base/effective/history/revision，並由既有 sessions.csrf 產生 token。卡片 HTML 六欄與原解析／依據可讀，官方連結不可編輯。private item 保留既有 detail 的 metadata contract，不改清單查詢／統計。

POST `/announcements/{announcement_id}/action-card/corrections`，表單欄為 csrf_token／operation／baseline_hash／expected_revision、六欄的 `<field>.mode/value/quote/confirmed`、action_decision／deadline_kind。最多 32 個欄位、總量 128 KiB；重複與未知欄拒絕。reset 使用獨立小表單，不因未儲存的壞日期阻止恢復。GET `/action-cards/history/{snapshot_id}?page=1` 僅本人，可看各 revision 與原快照，不建立新資料。

代表性頁面斷言（既有 web fixture 與 BeautifulSoup）：

```python
client, app, google, settings = web
response = client.get('/demo/announcements/demo-event')
card = BeautifulSoup(response.text, 'html.parser').select_one('[aria-label="公告行動資訊卡"]')
assert response.status_code == 200 and card is not None
assert '活動日期' in card.get_text() and '截止' in card.get_text()
assert '待確認' in card.get_text()  # 合成報名截止只有 9 月 18 日，不能猜年份
```

- [ ] 寫三類詳情測試：公開三種 Cookie 不解析 Session／私人表；demo 不查 DB；私人只取本人 Analysis。缺 AI／壞結果仍顯示卡片；六欄順序及截止／活動分離、pending 文案、原始解析與非高科大外鏈官方性待確認可見。GET 前後新表計數不變。
- [ ] 寫 POST 測試：登入本人＋有效 CSRF 儲存後 303 至自己的詳情；再 GET 顯示 user_confirmed 與舊解析。過期 Session 401、跨帳號與歷史 404、CSRF／Origin:null／跨站 403、內容類型錯 415、超大 413、欄位錯 422、來源／revision 衝突 409；均不得改資料。無效輸入留在繁中表單中且安全跳脫。
- [ ] 加入 Read Focus 5：讀修正／歷史發生 DB 錯誤回 503 與不完整提示，不能裝成零修正；來源原文可在已取得時閱讀。測試 `<script>`／`</script>`／引號於原文、AI、修正、嵌入 JSON 都不執行；歷史只供 owner。執行新測試，確認現有頁缺卡片／路由而失敗。
- [ ] 實作共享 card／editor／history／error 模板，Jinja 自動跳脫。供 public/demo JS 使用的 wrapper 格式 `{schema_version:1,scope,base_card,expected_revision,taipei_today}` 放在經 `tojson|forceescape` 的 data attribute；只在 public/demo 輸出，私人不用此裝置 payload。JS 後續只用 textContent 更新值。
- [ ] 掛載私人 router，使用既有 current_user、HMAC CSRF、Origin／Sec-Fetch-Site 與限量表單解析。成功 PRG；驗證／衝突回 owner-scoped HTML 保留白名單輸入，未登入及跨 owner 不回傳私人快照。GET 私人詳情採 same-origin Referrer-Policy 讓瀏覽器正常送 Origin，禁止放寬 Origin:null；其他路由安全契約不變。
- [ ] 表單用 ASCII percent-encoded body 及 strict UTF-8 解碼，禁止重複鍵；省略的 checkbox 視為 false，其餘具語意欄位不靠隱式字串轉 bool。history GET 的 page 為正整數，傳入服務的分頁參數明確為 `load_private_history(database, user, snapshot_id, *, page_number: int=1)`；匿名頁面採既有 303 登入導向，POST 未登入仍 401。
- [ ] 用 `ui-ux-pro-max` 核對手機排版、44px 操作與焦點；無 JavaScript 仍讀卡片並可提交私人表單。公開編輯此時先標為需裝置儲存，Task 4 才開啟。移除／改標舊詳情中會誤導的「未提供／是／否」重複區，保留原始值在原解析區。
- [ ] 跑 `tests/test_action_card_pages.py tests/test_public_pages.py tests/test_demo_pages.py tests/test_sessions.py tests/test_announcements_auth.py tests/test_account_controls.py tests/test_pwa.py`，期望 exit 0。提交 `feat: present action cards and authenticated corrections`。

## Task 4：公開裝置修正、示範與故障驗證（約 60–90 分鐘）

**Files:** 新增 `action-card-store.js`、`action-card.js`、`tests/action_card_store_check.cjs`、`tests/browser/action_card_store.html`；修改編輯模板／CSS／demo_notice 及示範測試。

**Interfaces:** store 模組輸出 `createActionCardStore({indexedDB}={})`（瀏覽器預設採原生工廠、測試可注入），回傳 `read(sourceRef): Promise<LocalRecord|null>`、`commit({card,patch,operation,expectedRevision,now}): Promise<LocalRecord>`、`erase(sourceRef,expectedRevision): Promise<void>`。`LocalRecord={schema_version:1,source_ref,revision,baselines:{[baseline_hash]:ActionCard},revisions:[{revision,baseline_hash,operation,patch,created_at}]}`。DB=`nkust-campus-assistant`、version=1、store=`publicActionCards`、keyPath=source_ref。

錯誤使用固定 code：STORAGE_UNAVAILABLE／STORAGE_QUOTA／STORAGE_CORRUPT／REVISION_CONFLICT。UI 必須有未保存狀態及重試，不將 read failure 轉 null。模組沒有 network 行為；scope=private 在呼叫工廠前結束，store 自身再拒絕非 public card。demo 使用頁面記憶體實作相同操作語意，reload 清空。

代表性 Node 斷言（node:assert/strict、store 模組的 CommonJS 匯出；瀏覽器使用同一 IIFE 命名空間，不增加 bundler）：

```javascript
let opened = false;
const store = createActionCardStore({indexedDB: {open() { opened = true; }}});
await assert.rejects(store.commit({card: {source: {kind: 'private'}}}), /PRIVATE_SOURCE_NOT_ALLOWED/);
assert.equal(opened, false);
```

store 對非 public card 回 TypeError('PRIVATE_SOURCE_NOT_ALLOWED')。action-card.js 另提供同步 `validateCorrectionPatch(raw)` 與 `applyLocalPatch(card, patch)`，共用 Node／瀏覽器匯出；只實作同一六欄修正語意與長度／ISO 日期驗證，不在 JS 重做來源日期抽取或產生新的 supported 狀態。壞紀錄須回 STORAGE_CORRUPT，不能當成不存在覆寫。

- [ ] 寫 Node 行為測試：未 commit 不保存、舊 baseline 歷史保留、舊預期 revision 被拒、交易完成前 Promise 不成功、put 後 abort 仍失敗、quota/open error 不覆寫舊資料、private card 被拒。新增頁面契約測試保證 private 不載入 store 腳本／payload，公開編輯內容不進 GET URL 或任何儲存 API。
- [ ] 建立只供本機合成測試 app 掛載的 browser harness：載入同一 store 模組，提供可點擊的原生 IndexedDB 保存／重載／重設／衝突及故障注入案例，結果寫到可見 DOM。不得新增正式測試路由或產品的故障開關。先跑 Node 新測試，預期缺模組失敗；browser 案例會先在未完成 store 時顯示失敗。
- [ ] 實作 IDB readwrite 交易：同一交易讀取版本、比較 expectedRevision、加入新 baseline／追加 revision、寫回同筆資料；只在 transaction.oncomplete resolve，abort/error reject。onblocked 提示關閉其他舊分頁，不直接刪 DB。erase 只刪明確選定來源，版本衝突不刪；UI 先顯示永久刪除修正歷史確認。
- [ ] 實作 UI：public 在首次儲存前明示裝置／共用瀏覽器限制，成功後才顯示已保存；未能讀既有紀錄時不允許覆寫。來源 baseline 不同顯示 stale，待再次核對並明確 save；reset 保留歷史。表單失敗留值，欄位變化標未保存；無 JavaScript 不顯示無法操作的編輯按鈕。
- [ ] demo 修正／恢復只改記憶體，重載回原始合成值，警語明示；private 不呼叫裝置模組且不使用任何持久化 browser storage。日期字串直接顯示，不透過 Date 造成 UTC／當地日偏移；保存時間標裝置記錄時間並用台北時區呈現。
- [ ] 用 `computer-use`／CUA 實際瀏覽器驗證 native IDB：公開 save→reload 保留；兩分頁同 revision 只有一方成功，另一方保留輸入並提示；來源變更不套舊值；reset 留歷史；demo reload 不保存。以注入 quota／abort 的 harness 在實際瀏覽器驗證錯誤，明列是故障注入，不填滿使用者真實儲存空間。私人登入 A→登出→B 不見 A 修正且不產生裝置資料。
- [ ] 核對 320／390px、Tab、依據展開、錯誤訊息及 JS 不可用的閱讀；保存只含合成資料的截圖。跑 Node store/filter/SW 檢查與 `tests/test_action_card_pages.py tests/test_demo_pages.py tests/test_pwa.py`，期望 exit 0。未能實測的瀏覽器條件不得宣稱通過。提交 `feat: keep public action card corrections on device`。

## Task 5：完整驗收、文件及交付（約 30–60 分鐘）

**Files:** README、`docs/public-announcements.md`、`app/templates/web/privacy.html`、phase2 validation 文件、必要的 PWA／版本測試與本計畫 checkbox。

**Interfaces:** 消費前四 task 的實際路由、DTO、保存結果，產出可獨立閱讀的使用／隱私說明、migration 界線與驗收證據。

- [ ] 文件分清楚第一階段已完成、本次第二階段本機功能、歷史發布紀錄與正式現況。公開裝置保存、共用瀏覽器風險、清除會遺失；私人帳號保存／刪除及備份限制；示範記憶體重載清空；多人沒有啟用新 AI／抓全文；日期及資格待確認的限制均需可找到。
- [ ] 跑完整 pytest（每輪新 basetemp）、三項 Node 檢查及 `git diff --check`；核對 0006→0007 與 owner FK／重解析／衝突測試證據。專用 PG 不存在明列 skipped；離線 SQL 不稱 PostgreSQL 實測。不因 schema head 變更而放寬舊私人安全斷言。
- [ ] 依 `requesting-code-review` 做一次全變更範圍的新上下文唯讀審查，提供規格、計畫、Review Focus 與 ledger 裁定。重大／重要項目在一輪修正中補重現測試、RED→GREEN、完整回歸；小項記錄延期。依 `verification-before-completion` 只憑實測宣稱完成。
- [ ] 精確指定本階段檔案建立本機提交；不包含既有 Dashboard／字型／readiness 修改。依使用者限制保留本機分支／工作區，不 push、不部署、不執行正式 migration。清理本計畫自建的暫時預覽與 ledger，保留已提交證據，不刪其他計畫或使用者資料。
- [ ] 報告第二階段現在可用的行動卡、修正與保存，附測試結果、限制與截圖；下一步才進第三階段待辦設計，不自動把卡片轉成待辦。未完成的驗收項目必須明列，不能僅因程式寫完就稱完整完成。

## 自我審閱與執行交接

規格覆蓋：欄位／來源／AI／日期 → Task 1、3；私人快照／重新解析／帳號／migration → Task 2、3；公開裝置／demo／多分頁／錯誤 → Task 4；手機／原文／無 JS → Task 3、4；文件／獨立審查／不部署 → Task 5。Review Focus 五項各有對應的失敗案例，不將規格沉默視為可忽略的輸入。

介面核對：六個 CardField 鍵、deadline_kind、CorrectionPatch、revision_count、expectedRevision／expected_revision 只在 JS／Python 邊界明確轉換；私人 POST 的 baseline_hash 只作相等檢查，來源與 owner 由伺服器取得；動態台北日期不進基準 hash。原文資料不在兩種保存區之間搬移。

範圍是一個可驗收的第二階段功能，五項任務有順序依賴；不拆成新的聊天或並行實作者。估計 5–7 小時（基線可執行、PostgreSQL 未另行安裝），實際測試與瀏覽器結果影響時程。

狀態：計畫已自我審閱，待使用者確認是否符合需求；執行方式已確定為本對話 inline，無需重新選擇。
