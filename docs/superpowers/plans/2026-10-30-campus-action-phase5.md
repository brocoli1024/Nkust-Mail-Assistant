# 來源關聯與版本留存 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，沿用本對話inline，不派每項實作者；一次fresh全範圍review。

**Goal:** 官方URL可靠相同才整理來源，原文與更新歷史不遺失，私人內容不進公開區。

**Architecture:** read-time logical grouping，public/private獨立append版本表，接入現有同步lease交易，不實體合併、不新服務。

**Tech Stack:** FastAPI/Jinja、SQLAlchemy/Alembic、原Python日期／來源模組、pytest/原Node回歸。

**Spec:** docs/superpowers/specs/2026-10-30-campus-action-phase5-design.md

## Global Constraints

- 僅可信https NKUST明確文章URL，fragment去除後完全相同；path/query保留，不用標題／RSSGUID自動合併。
- 不刪來源、不搬私人資料到公開／裝置、不改修正／待辦／ICS。公開頁不解析Session／私人表。
- migration0009只在合成測試庫，不部署／push／正式DB／OAuth／付費／新依賴。
- 時間標台灣留存時間，不冒稱官方更新；未知日期待確認，parser差異非必然內容更新。
- 原基準與新版本同交易，失敗rollback；GET零寫入，各類每頁20筆，舊ID失效仍可尋歷史。

## Review Focus

1. 官網清單／首頁同URL、query或頁型差異、相似標題，不能錯誤關聯（Task1）。
2. A→B→A與既有資料首留基準、來源失敗／交易失敗，不能丟失／虛構歷史（Task2）。
3. 私人重解析索引／ID重用、他人相同URL、Google身分過期與刪帳號，owner不可錯（Task2/3）。
4. pending日期與parser-only差異，不可宣稱官方改期；私人更新不影響公開歷史（Task1/3）。
5. 多於20筆、來源紀錄讀取錯誤、匿名cookie與XSS，不能漏入口／假空白／洩漏（Task3/4）。

## Task1：身份／快照／差異純函式

**Files:** app/services/source_history.py、tests/test_source_identity.py。
**Interfaces:** official_identity(url)->str|None；public_snapshot(row)->dict；private_snapshot(row,email,parser_version=None)->dict；snapshot_changes(old,new)->list[str]。snapshot={source_kind,url,title,text,html,metadata,card}，public html永遠null，private保留原HTML但只以escaped pre顯示。metadata含原發布或收到時間、來源parser及原解析，排除last_seen/captured等揮發欄位；card是未套個人修正的純原文解析。

- [x] 寫URL及差異測試Expected缺module RED：可信文章fragment相同、不同query/path/host不相同、列表／http／外站／同標題不關聯、明確期限舊新與pending/parser-only文案。
- [x] 實作上述接口，沿用normalize_public_url／build_action_card，不連網或呼叫AI。
- [x] 跑pytest tests/test_source_identity.py Expected exit0，提交feat: identify conservative official source groups。

## Task2：版本模型與同步交易

**Files:** app/models/source_history.py、alembic/versions/0009_source_history.py、tests/test_source_versions.py、可選tests/test_source_history_postgresql.py；修改alembic/env.py、schema.py、public_sync.store_entries、UserMailRepository.save_processed、PG offline downgrade範圍。
**Interfaces:** record_public_version(session,row,now,*,baseline=False)->None；record_private_version(session,row,email,now,*,parser_version=None,baseline=False)->None。V={id,source_key/url(public)或user_id/email_id/source_index/source_fingerprint(private),snapshot_hash,snapshotJSON,captured_at,baseline bool}；private owner FK Email CASCADE，無Announcement FK。最新相同snapshot不追加，重返舊內容仍追加。Public helper拒絕非PublicAnnouncement。

- [x] 寫新版本測試RED：公開A/B/A／重跑／preexisting基準／fail不改；private實際repo force重新解析留舊／新、原HTML與parser、他人URL不相混、刪帳號不動public/B；inject留存失敗rollback；版本皆有captured時間。
- [x] 實作additive0009及metadata註冊，schema要求0009。public舊row變更前留基準、更新後留新；private copy email前留舊、加入新announcement後留新（傳正確新parser）；同一現有lease交易，不額外commit。
- [x] 跑 source_versions + public_sync + sync_multi_user + multi_user_database + postgresql_readiness Expected exit0；專用PG缺少明列skip。提交feat: preserve isolated public and private source versions。

## Task3：權限查詢、變更與分頁頁面

**Files:** app/services/source_views.py、app/api/source_history.py、source_history.html、source_group.html、source_version_detail.html、tests/test_source_history_pages.py；修改web.py、兩種detail模板、site_header、CSS。
**Interfaces:** public_history(database,pid,page_number=1)->dict（只P/PublicVersion）；private_history(database,user,page_number=1)->dict；private_version(database,user,vid)->dict；related_sources(database,user,aid,page_number=1)->dict。沿用_identity驗證Google subject，錯owner CorrectionNotFound，SQL/schema／壞snapshot CorrectionUnavailable。所有page>=1 le1000000，20+1取頁有has_more，版本詳細來源清楚且escaped。關聯頁查本人URL候選後以official_identity再次驗證精確相等，query不模糊合併；公資料仍只SOURCE_KEY來源。

- [x] 頁面／查詢RED測試：同URLpublic+A、排B，同標題不同URL分開；invalidURL無關聯；匿名publichistory不讀session/private；privateowner404、invalidsubject404、GET不寫、503不假空白；21筆各頁可發現；期限／原文／HTML跳脫與版本解析標示。
- [x] 實作上述四個GET路由／模板與detail/nav入口；不加寫入API。來源與歷史只展示被授權的資料，不改原card／todo。
- [x] 跑source_history_pages及前四階段頁面／安全回歸Expected exit0，提交feat: show owner-scoped related sources and history。

## Task4：合成瀏覽器、審查、文件

**Files:** tests/browser QA僅合成資料入口、README/privacy/public-announcements、phase5驗證文件、此計畫。
- [x] QA seed同官方文章URL的公開及A/B私人不同原文，留public前後期限及private版本；browser驗證分區、差異、版本、A登出B隔離、320/390與焦點及合成截圖。
- [x] 完整pytest新basetemp、原六Node及diff --check；migration0009限定測試，明列PGskip。
- [x] 一次fresh唯讀全range reviewer，Critical/Important一輪RED→GREEN+全回歸，minor延期；不重派review。
- [x] 文件寫首次留存基準非完整歷史、文章URL保守範圍、日期與先後不確定、owner刪除／備份；本機提交保留worktree，停止QA、不push。先保存rulings再清本計畫scratch。

Self-review：純snapshot feed同步與diff；public/private記錄helper獨立表不可交叉，group只讀本人。versions不依重用AID；ownerFK維持刪帳號隱私。既有資料不偽造回溯，public匿名不加private count。需求及inline已由使用者本對話指定，沿用不重核授權。
