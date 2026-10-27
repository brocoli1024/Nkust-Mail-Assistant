# Public and Private Announcements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. User approved Native execution on 2026-10-27. Implementation and local verification completed; PostgreSQL execution and formal deployment remain unverified. See [validation record](../../public-announcements-validation-2026-10-27.md).

**Goal:** 提供免登入的公開校園公告，全部收錄並提供學生相關篩選，同站保留私人 Gmail 公告。

**Architecture:** 公開資料使用多人資料庫中的獨立表，不改私人表的帳號限制。官方 RSS 提供近期增量，經驗證的清單分頁提供可續跑的歷史補收；兩者共用公開資料寫入服務。公開與私人清單分開呈現，共用既有視覺與可重用分類函式。

**Tech Stack:** Python、FastAPI、Jinja2、SQLAlchemy、Alembic、SQLite / PostgreSQL、httpx、BeautifulSoup、pytest；XML 使用 defusedxml（加入前核對官方套件來源及鎖定版本）。

**Spec:** [已通過設計](../specs/2026-10-27-public-and-private-announcements-design.md)

## Global Constraints

- 指定來源為 `https://www.nkust.edu.tw/p/422-1000-1001.php`；RSS 為 `https://www.nkust.edu.tw/p/503-1000-1001.php`。
- 全部收錄，再提供學生相關篩選；不因分類或學生相關判斷而拒絕收錄。
- 「全部」限指定清單可取得的內容，不宣稱涵蓋全校所有網站、所有 Gmail 或尚未補收的歷史。
- 來源文字、摘要以跳脫文字顯示；不公開私人郵件，不放寬 `user_id` 約束，不提供匿名抓取或寫入入口。
- 初期由維護者 CLI 更新；不新增付費服務或未經確認的自動排程。RSS 消失不等於刪除。
- 使用新增 migration `0006`；只在獨立測試庫驗證，不讀寫正式 Neon、真實 Gmail、現有資料庫及 token。
- 保留工作目錄原有 Dashboard CSS / JS / HTML、字型及 readiness 文件修改。執行時先使用 using-git-worktrees 技能建立隔離工作目錄，將已審閱 spec / plan 複製至該工作目錄，不能遺失這兩個未追蹤文件。

## Review Focus

1. RSS 截斷、空資料、HTML 錯誤頁不能造成清空資料或假成功（Task 1 / 3）。
2. 相同標題、不同來源 URL 不能錯合併；來源識別碼變動不能產生重複（Task 2 / 3）。
3. 類似學生詞彙的教師研習、模糊公告及沒有摘要的公告不能被當成確定相關（Task 4）。
4. 歷史清單翻頁重複、來源變動、中途失敗不能誤標歷史完整（Task 6）。
5. 登入 cookie、帳號刪除與猜測 ID 不能使公開路由洩漏私人內容或刪掉公開資料（Task 5 / 7）。

## File Structure and Interfaces

| 檔案 | 責任 |
| --- | --- |
| `app/services/public_source.py` | 固定來源設定、安全傳輸、RSS 與清單解析；不連資料庫 |
| `app/models/public_announcements.py` | 獨立公開表，使用 `MultiUserBase` |
| `alembic/versions/0006_public_announcements.py` | 僅新增公開表、索引及約束 |
| `app/database/schema.py` | `REQUIRED_REVISION = '0006'`，供 web / preflight 共用 |
| `app/services/public_sync.py` | 公開 upsert、同步紀錄、交易與補收游標 |
| `app/services/student_relevance.py` | 純函式，相關 / 不明 / 明確非學生及命中原因 |
| `app/public_cli.py` | 獨立維護命令，不載入舊單人 AI / scraper 指令 |
| `app/api/public_announcements.py` | 公開唯讀清單與詳情，查詢只使用公開表 |
| `app/templates/web/public_home.html`、`public_announcements.html`、`public_announcement_detail.html` | 公開首頁、清單與詳情 |
| `docs/public-announcements.md` | 維護指令、收錄範圍、補收與失敗處理 |

跨任務資料型別於 Task 1 定義：

```python
@dataclass(frozen=True)
class PublicEntry:
    title: str
    url: str                  # validated absolute original URL
    published_at: datetime | None  # aware UTC; never substitute fetch time
    excerpt: str              # source text only, not AI output
    external_id: str | None   # opaque source identifier, not assumed unique across sources

class PublicSourceError(RuntimeError):
    pass                      # fixed codes only
```

URL 唯一性使用來源鍵 `nkust-latest` 與保守正規化 URL；只移除 fragment / 預設 HTTPS 443、正規化 hostname，保留 path、query 值與順序。來源 GUID 只保存作追蹤，不單獨當主鍵。

## Task 1: Verify Source Contract and Implement a Bounded RSS Adapter

**Files:** Create `app/services/public_source.py`, `tests/test_public_source.py`, `tests/fixtures/public_source/`; modify `requirements-web.txt` and test dependency lists only as needed.

**Interfaces:** `parse_feed(data: bytes) -> list[PublicEntry]`; `normalize_public_url(value: str) -> str`; `fetch_feed(*, transport=None) -> bytes`。HTTP / parser dependency injected for offline tests.

- [ ] 查閱 RSS / robots / 網站使用說明，記錄最終 URL、狀態、content type、XML 編碼、item 數、guid / link 格式、摘要是否截短。只做少量讀取；取得條件不明確時記錄未決事項，不大量回補。
- [ ] 保存合成 XML fixtures；真實來源樣本只保留最少必要結構，不提交聯絡資料或真實郵件。
- [ ] 寫失敗測試 `test_rss_extracts_title_date_link_and_plain_excerpt`：一則合成 item 解析後 title 正確、HTTPS 原文 URL 正確、日期為 UTC、HTML 摘要無標籤。另測試不同來源時區、未知日期保留 None、XML entity / DTD 被拒、錯誤 HTML / 截斷 XML / 超限輸入報固定代碼。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_public_source.py -q -p no:cacheprovider`；應因新介面未存在而失敗。若 tmp fixture 權限失敗，先診斷路徑，使用全新且可寫的 basetemp，不把環境錯誤當產品失敗。
- [ ] 實作安全 XML 解析、純文字摘要及傳輸限制：2 MiB 解壓後本文、最多 500 items、每欄 title 2000 / URL 4096 / excerpt 12000 字、connect 5 秒 / read 20 秒、整個下載總限 30 秒、最多 3 次手動驗證轉址；超限不靜默截斷成成功。固定 HTTPS `www.nkust.edu.tw` / 443 的下載端點，拒絕憑證錯誤、credentials、非公開 DNS 及轉址到其他 host。每次連線驗證實際目的地，避免僅檢查 DNS 後由 HTTP client 再解析造成繞過；可重用經驗證傳輸機制，不能為方便而關閉 TLS。
- [ ] 原文連結只接受 HTTPS、無 credentials / 非預設 port，hostname 僅 `nkust.edu.tw` 或以 `.nkust.edu.tw` 結尾。保存連結不代表自動抓取該站；非符合條目計入明確失敗，不默默漏收。
- [ ] Run 相同測試，確認通過；取得一批 live feed 做唯讀解析，記錄結果與缺口。若資料無法取得，仍完成離線合約，但不宣稱 live 同步可用。
- [ ] 檢查本任務 diff 後 commit，僅 stage 此任務明列檔案。

## Task 2: Add Public Storage and Schema Compatibility

**Files:** Create `app/models/public_announcements.py`, `app/database/schema.py`, `alembic/versions/0006_public_announcements.py`, `tests/test_public_database.py`; modify `alembic/env.py`, `app/web.py`, `app/deployment_check.py`, `tests/test_postgresql_readiness.py`.

**Interfaces:** `PublicAnnouncement`, `PublicSyncRun`, `PublicSourceState` ORM classes registered in `MultiUserBase.metadata`。`REQUIRED_REVISION` replaces duplicated `'0005'` checks.

- [ ] 寫 `test_public_rows_have_no_user_dependency`：不建立 User 可插入公開公告；刪除合成 User 不影響公開公告。測試 `(source_key, canonical_url)` 唯一、標題相同 URL 不同可共存、migration 0005→0006 不改私人資料、metadata 無 drift。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_public_database.py -q -p no:cacheprovider`，確認因新表未存在失敗。
- [ ] 實作公開表：id、source_key、canonical_url、external_id、title、published_at、excerpt、category、category_rule_version、student_relevance、student_reason（JSON）、student_rule_version、content_hash、first_seen_at、last_seen_at、updated_at。狀態三值 `relevant / not_student / unknown`，預設 unknown。
- [ ] 同步表存 id、source_key、mode、status、started_at、finished_at、added、updated、unchanged、failed、error_code。來源狀態表存 source_key、last_success_at、oldest_seen_at、next_history_page（預設 1）、history_status（not_started / incomplete / complete）、lease_owner / lease_expires_at（供 Task 3 原子鎖）。必要狀態加 check 約束，時間使用 timezone-aware。
- [ ] 新增 migration 0006 / down_revision 0005，只新增公開表；載入 metadata 時避免 circular import。離線 downgrade 測試起點改為 0006。同步更新 schema revision 與既有測試對 `/` 的新預期（公開首頁在 Task 5 才落實）。
- [ ] Run public database、multi-user database、deployment check、PostgreSQL compilation 測試；獨立測試 PostgreSQL 可用時執行實機 migration。skip 只記未驗證。
- [ ] 檢查 diff 後 commit。

## Task 3: Implement Idempotent RSS Sync and Maintainer CLI

**Files:** Create `app/services/public_sync.py`, `app/public_cli.py`, `tests/test_public_sync.py`, `tests/test_public_cli.py`.

**Interfaces:** `SyncResult(added: int, updated: int, unchanged: int, failed: int, status: str)`；`sync_recent(database, *, source=fetch_feed, now=None) -> SyncResult`；CLI `main(argv=None) -> int`。

- [ ] 寫 `test_sync_repeat_update_and_source_failure`：首次合成 feed added=2，重跑 unchanged=2，改一則摘要 updated=1；後續來源逾時保留原公告及 last_success_at。測試空 feed 不報成功、malformed item 記 partial、同標題不同 URL 不合併、lease 阻止同時同步、崩潰後 lease 到期可恢復。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_public_sync.py tests/test_public_cli.py -q -p no:cacheprovider`，確認紅燈來自缺少功能。
- [ ] 交易內 upsert，內容 hash 排除抓取時間；first_seen 不變，last_seen 每次有效觀察更新，updated_at 僅內容變動更新。部分成功可提交有效條目，但 run 記 partial、failed 數正確，不更新 last_success_at。
- [ ] 以來源狀態列的條件更新取得 10 分鐘 lease，owner 隨機值、到期時間 UTC。每個寫入交易核對 owner 與未到期，釋放時核對 owner，不能只用程序內鎖。取不到回固定 `PUBLIC_SYNC_BUSY`。
- [ ] CLI `python -m app.public_cli sync --source nkust-latest` 僅使用 Settings 的多人 DATABASE_URL，先檢查 revision，且不得自動 migration。stdout JSON 只含計數及固定代碼，失敗 / partial / busy exit 1；參數錯誤 exit 2。不得列出 DB URL、郵件或 token。
- [ ] Run 上述測試，加上未帶 Google / AI 金鑰也能在獨立多人測試庫跑 CLI 的測試。對合成資料驗證 CLI，不連正式庫。
- [ ] 檢查 diff 後 commit。

## Task 4: Add Conservative Student Relevance and Shared Categories

**Files:** Create `app/services/student_relevance.py`, `tests/test_student_relevance.py`; modify `app/services/public_sync.py`.

**Interfaces:** `classify_student_relevance(title: str, excerpt: str) -> RelevanceResult`，結果包含 status、reasons（字串代碼 tuple）、rule_version。`RULE_VERSION = 'nkust-student-rules-v1'`。

- [ ] 寫 `test_scholarship_is_relevant_and_teacher_workshop_is_not_student`：獎助學金申請 relevant；明確「教師專屬研習」not_student；僅「研究計畫說明會」unknown；同時明列師生參與 relevant；只有「講座」unknown。另測無摘要、空字串及混合全半形。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_student_relevance.py -q -p no:cacheprovider`，確認缺少功能失敗。
- [ ] 以純規則判斷，Unicode NFKC 正規化；明確混合師生優先、學生明確證據其次、教師專屬其後，其餘 unknown。規則清單保存具體命中原因，不能把「一般徵才」自動當學生實習。重用 `classify_category('', title)`；分類不明仍保存。
- [ ] 整合同步時記錄兩種分類版本；新增 CLI `reclassify --source nkust-latest`，只重算公開表、不網路請求。同步及重分類共用來源 lease。
- [ ] Run relevance / public sync / CLI 測試；檢查 diff 後 commit。

## Task 5: Serve Public Pages and Integrate Navigation

**Files:** Create `app/api/public_announcements.py`, `app/templates/web/public_home.html`, `public_announcements.html`, `public_announcement_detail.html`, `tests/test_public_pages.py`; modify `app/web.py`, `app/templates/web/site_header.html`, `app/templates/web/login.html`, `app/templates/web/privacy.html`, `app/static/web/account.css`, `tests/test_sessions.py`, relevant root-route tests.

**Interfaces:** GET `/` → public homepage 200；GET `/public/announcements?q=&category=&audience=all&page=1`；GET `/public/announcements/{id}`。audience 僅 all / student，student 查 relevant；page >=1、page size 20、q <=200、category 使用既有 CATEGORIES / 未分類。

- [ ] 寫 `test_anonymous_public_pages_never_resolve_private_sessions`：seed public marker + private marker，未登入 / 假 cookie / 真 cookie 訪問公開路由只得 public marker；mock session resolve 為失敗也不影響公開頁。相同數字私人 ID 不可經公開詳情取得。未登入私人頁仍 303 / API 401。
- [ ] 加 `test_student_filter_does_not_delete_unknown_rows`：預設含 relevant / unknown / not_student，篩選只 relevant，清除後全部重現；確認關鍵字 / 分類 / 翻頁可組合，未知參數值 422，缺 ID 404，POST 公開清單 405。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_public_pages.py -q -p no:cacheprovider`，確認預期失敗。
- [ ] 實作公開查詢，只匯入公開 ORM；首頁無論 cookie 都回 200，登入入口仍是 `/login`。首頁顯示 NKUST Mail Assistant、公開資料用途、隱私連結、私人功能入口；不要暗示已通過 Google 驗證。
- [ ] 公開頁顯示發布日期（未知不猜）、最後成功更新、RSS 近期 / 歷史補收狀態、分類及來源連結；摘要來源可能截短，不顯示為全文。學生篩選提示「依內容規則判斷，可能漏判；可切回全部」。未知 deadline 不渲染倒數。
- [ ] 第一版不顯示推定登入者個資，公開導覽提供公開公告 / 我的郵件連結，私人頁維持原導覽。保留 HTML escaping；標題 / 摘要含 `<script>`、link `javascript:`、屬性注入都不執行。
- [ ] 隱私頁補充公開來源及私人資料邊界；PWA worker 不新增公告快取。Run public pages、sessions、account controls、user isolation、PWA 測試；測試中刪合成帳號後公開資料仍存在。
- [ ] 使用合成資料在 375px / 1280px 瀏覽器檢查空清單、長標題、鍵盤焦點、篩選、分頁與原文連結，依 ui-ux-pro-max 技能延用現有設計。檢查 diff 後 commit。

## Task 6: Verify and Add Resumable History Backfill

**Files:** Modify `app/services/public_source.py`, `app/services/public_sync.py`, `app/public_cli.py`; create `tests/test_public_history.py`, sanitized history fixtures.

**Interfaces:** `parse_listing(data: bytes, *, page_number: int) -> ListingPage(entries: list[PublicEntry], has_next: bool)`；`backfill_history(database, *, max_pages: int = 5, source=None, now=None) -> SyncResult`。

- [ ] 先少量觀察真實第 1 / 2 頁及最後頁控制，驗證實際分頁 URL / 請求方法、日期、原文 URL 與 RSS 對應。不能猜 `javascript:void(0)` 的 request。只接受固定來源讀取；來源條件不允許時記錄 blocked，不批次擷取。
- [ ] 寫 `test_backfill_resumes_only_after_committed_page`：三頁合成清單，第二頁失敗時游標停 2、第一頁保存；重試新增第二頁，不重複第一頁。測試頁面重複 fingerprint、非空合法末頁、空 / malformed 頁不得假 complete。
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_public_history.py -q -p no:cacheprovider`，確認預期失敗。
- [ ] 使用已觀察到的分頁合約讀取清單，重用 PublicEntry 與 upsert；清單沒有摘要時不得清空 RSS 已存摘要。每頁提交後推進 next_history_page；固定來源 lease、頁數最多 20 / 次、預設 5、請求間隔至少 2 秒、最多 120 秒 / 次，逾時記 incomplete 並可續跑。翻頁全局變動期間只顯示「已完成一次歷史掃描」，不承諾絕對無缺漏。
- [ ] 無法驗證的分頁先以固定 `PUBLIC_HISTORY_UNVERIFIED` 拒絕 backfill，不提供猜測實作。這是明示的來源阻礙，不算全部收錄完成；近期 RSS 功能仍可交付。實際 completion 只在合法末頁且未發生漏項時設定，保留 oldest_seen_at 及 sweep 時間。
- [ ] CLI `python -m app.public_cli backfill --source nkust-latest --max-pages 5`；Run history / sync / CLI 測試，PostgreSQL 驗證 lease 和競爭時游標不倒退；檢查 diff 後 commit。

## Task 7: Verify the Integrated Deliverable and Write Operations Guide

**Files:** Create `docs/public-announcements.md`; modify README 開頭、多人成署手冊 `docs/multi-user-phase9.md`。readiness 歷史文件已有使用者修改，不直接重寫。

- [ ] 文件說明部署需 migration 0006、執行 RSS sync / backfill / reclassify 指令、狀態欄含義、日期未知及來源範圍、無排程承諾、Google 私人功能仍受授權限制。web requirements 若新加 XML 套件，文件寫清楚安裝路徑。
- [ ] Run `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`，記錄 passed / skipped / warnings；若本機測試暫存權限失敗，先依 systematic-debugging 技能定位並在全新可寫目錄重跑。對能運行的相關測試取得完整結果，不直接中斷後宣稱通過。
- [ ] 在獨立 PostgreSQL 測試庫執行 migration、public database / sync / history 與現有隔離 / 刪除案例；若不可用，明列未實機驗證，不把離線 SQL 編譯當實機通過。
- [ ] Run `git diff --check`；檢查新增檔案、dependency diff、migration revision、公開與私人權限邊界。先用 requesting-code-review 技能完成適用複查；執行方式與 reviewer 選擇以使用者確認為準，不自行更換模型。
- [ ] 瀏覽器驗證匿名公開入口、手機寬度、學生篩選、登入後私人導覽；保存不含真實郵件的畫面。只使用合成資料。
- [ ] 交付程式與證據，列明近期收錄 / 歷史補收實際狀態及已知缺口。正式 Render / Neon 部署需先核對正式備份及使用者授權；本計畫不自動執行正式 migration、真實同步或公開發布。
- [ ] 檢查最後 diff 後 commit；使用 finishing-a-development-branch 技能提出整合選項，不自動合併正式分支。

## Self-Review / Handoff

- 已對照設計：全收錄、學生可清除篩選、獨立公開資料、私人隔離、CLI 維護、歷史續跑與失敗可見均有任務。
- 第一批 RSS 可驗收近期功能；歷史來源未驗證時 Task 6 必須明列未完成，不以近期功能代替全部歷史承諾。
- 每個 Review Focus 已配對具體測試。Schema revision 0005 的 web / preflight 重複常數及現有 `/` 導向測試均列入更新。
- 本計畫尚未執行、未建立 worktree、未新增依賴、未變更 DB、未部署。
- 建議 Native 執行：由目前代理在同一聊天逐項實作，最後安排獨立複查。另一選擇是 Subagent-driven，每項任務由獨立代理實作與複查，成本較高。等待使用者審閱計畫並選擇方式後開始。
