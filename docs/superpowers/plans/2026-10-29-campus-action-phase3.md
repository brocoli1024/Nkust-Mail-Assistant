# 我的待辦 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，在本對話逐項實作，不派每項實作者。

**Goal:** 免登入找到公告→核對行動與期限→明確加入待辦→完成／稍後／移除。

**Architecture:** 公開待辦留原生 IndexedDB，私人待辦以 owner-bound SQL 保存。共用純日期及狀態語意，沿用行動卡及原有表單／Session，不新增服務。

**Tech Stack:** FastAPI、Jinja、SQLAlchemy、Alembic、原生 JavaScript／IndexedDB。

**Spec:** docs/superpowers/specs/2026-10-29-campus-action-phase3-design.md

## Global Constraints

- 不部署、push、正式 migration、OAuth 變更、新依賴或付費服務。介面繁中、44px 操作、手機與錯誤提示。
- 只有按加入才建立待辦；系統辨識不等於已加入。不判定資格，不升級未知日期。
- 公開裝置與私人帳號分區，不自動匯入或合併；demo 記憶體重載清空。
- 稍後固定明天09:00 Asia/Taipei，按前顯示確切時間；到期重新開頁或每分鐘重新計算，無推播承諾。
- 狀態移除採 tombstone 保存版本防 ABA；不刪來源公告／修正。重新加入保留同一來源身份，換來源不以相似標題合併。

## Review Focus

1. 移除後重新加入、兩分頁競爭不得復活舊狀態或無聲覆寫（Task1、3）。
2. 台灣跨日、UTC無時區、年底及截止早於稍後時間不得算錯（Task1、3）。
3. 舊 IndexedDB v1 升級 v2 保留修正，舊頁 blocked／VersionError 必須明示失敗（Task3、4）。
4. 私人來源重解析／帳號刪除與 Google 身分更換，不可改到其他資料；修正版本在加入前變動須回衝突（Task1、2）。
5. JS停用／儲存損壞／資料庫失敗不能呈現假空白或假成功（Task2、3、4）。

## Task 1：狀態、日期及私人保存

**Files:** 新增 app/services/todos.py、app/models/todos.py、alembic/versions/0008_private_todos.py、tests/test_todos.py；修改 alembic/env.py、app/database/schema.py、PostgreSQL downgrade 範圍。

**Interfaces:** next_snooze(now:datetime)->datetime(UTC)；todo_view(record:dict,now:datetime)->dict（effective_status、deadline_group、snooze_label）。list_private_todos(database,user,now=None)->list[dict]；get_private_todo(database,user,source_ref)->dict|None；add_private_todo(database,user,aid,expected_revision,baseline_hash,card_revision,now=None)->int；update_private_todo(database,user,tid,operation,expected_revision,now=None)->int。例外沿用 CorrectionNotFound／Conflict／Unavailable。

private_todos：id、user_id/email_id複合FK CASCADE、source_ref、source_index/fingerprint、card JSON、status active/done/snoozed/removed、snoozed_until、revision、created_at/updated_at；unique(user_id,source_ref)、positive revision、state checks。原卡與修正先核對 server source＋baseline＋card_revision，在 User 鎖內保存有效卡，未改來源表。移除保留 tombstone；re-add 只接受最新 revision。

- [ ] 寫 tests/test_todos.py：next_snooze UTC2026-10-29T16→台灣10/31 09（UTC10/31 01）；今日／逾期／七日邊界，pending日期不算deadline；GET零寫入、明確加入、重複／版本衝突、完成重開稍後移除重加、owner/oldGoogle-sub、刪帳號、重解析與修正版本衝突、兩寫入一成功。
- [ ] 跑 pytest tests/test_todos.py：Expected 缺模組 RED。
- [ ] 實作上述模型／純函式／服務，metadata註冊，0008只新增一表，不碰正式設定庫。
- [ ] 跑 tests/test_todos.py tests/test_multi_user_database.py tests/test_action_card_corrections.py：Expected exit0，提交 feat: persist explicit owner-scoped todos。

## Task 2：私人待辦表單與總覽

**Files:** 新增 app/api/todos.py、todo_controls.html、private_todos.html、todo_rows.html、tests/test_todo_pages.py；修改 correction renderer、action_card.html、session.py、account.html、site_header.html、web.py／CSS。

**Interfaces:** GET /my/todos?view=active|snoozed|done；POST /announcements/{aid}/todos（csrf、baseline_hash、card_revision、expected_revision）；POST /my/todos/{id}（csrf、operation complete|reopen|snooze|remove、expected_revision）。所有寫入同來源／CSRF、urlencoded、4KiB、最多8欄，未知／重複拒絕；成功303，版本409、登入401、owner404、錯誤503。頁面讀取不寫庫。detail 私人不用裝置模組，/dashboard 先呈現本人待辦及即將截止。

- [ ] 寫頁面測試：本人加入與狀態、CSRF／Origin:null／cross-site／未登入／錯 owner、錯revision、錯格式／超大／未知欄、來源安全跳脫、匿名不查私人資料、失敗503不當空白。
- [ ] 跑新測試 Expected 路由404／缺UI RED。
- [ ] 實作上述路由、模板及首頁接線，正常 HTML 表單無JS可用；private僅載入非持久化的到期重整腳本，每分鐘檢查是否需重整。
- [ ] 跑 tests/test_todo_pages.py tests/test_sessions.py tests/test_account_controls.py tests/test_action_card_pages.py：Expected exit0，提交 feat: add private todo controls and overview。

## Task 3：公開裝置／示範待辦與首頁

**Files:** 新增 app/static/web/todo-store.js、todos.js、todo-clock.js、public_todos.html、device_todos.html、tests/todo_store_check.cjs；修改 action-card-store.js、action-card.js、public_home.html、detail模板、demo、public route、header。

**Interfaces:** JS createTodoStore({indexedDB}) -> readAll(), change({operation add|complete|reopen|snooze|remove,card?,sourceRef,expectedRevision,now}):Promise<Record>。record={schema_version:1,source_ref,card,status,snoozed_until,revision,created_at,updated_at}；public only。DB原名version2，publicTodos keyPath source_ref；兩種store opener皆建缺失store但不清舊表。同步 validate／projectTodo／nextSnooze 以 Node 匯出驗證。純日期字串不經當地日轉換。

公開 action-card.js 每次 paint 將有效卡傳給同頁 todo controller（記憶體API，不傳網路）；保存來源 link local path由scope/id正確指定。加入前若有未儲存修正提示先儲存，不能偷用未儲存輸入。公開首頁及 /todos 只讀裝置DB；詳情載入已存修正後才啟用加入。demo記憶體替代，同頁完成／重開／稍後／移除，重載清空。

- [ ] Node RED：缺模組；之後測台灣跨日／未知日期、CAS重加防ABA、private拒絕、put後abort/quota不假成功、壞紀錄拒絕、v1修正store保留。
- [ ] 實作transaction complete才成功，錯誤留既有資料且明確重試，操作成功後refresh可見清單。各頁每分鐘投影稍後狀態，不自動寫資料。
- [ ] UI加入獨立裝置／帳號導覽，首頁待辦優先、七日截止／逾期與空白狀態。繁中按鈕44px，移除前確認且只改todo，示範明確標記。
- [ ] Node todo/store/filter/SW全通過；相關公開／demo／PWA pytest exit0，提交 feat: track public todos on device。

## Task 4：瀏覽器驗收、獨立審查與文件

**Files:** tests/browser 合成harness、README、privacy、phase3驗證文件、此計畫checkbox。

- [ ] 擴充本機QA入口、原生IDB harness驗證v1→v2保留修正、加入重載、雙分頁、abort/quota、稍後回到active、demo重載重設、私人換帳號與無私人裝置保存；320/390px、焦點及錯誤狀態，截圖僅合成資料。
- [ ] 完整 pytest新basetemp、四項 Node、diff --check，專用PG無設定則明列skip，不宣稱發布驗收。
- [ ] 一次 fresh whole-range 唯讀 reviewer（executing-plans允許）；Critical/Important一輪RED→GREEN修正後全回歸，minor記錄延期，不派第二審。
- [ ] 更新功能／保存界線、未部署與第四五階段設計保留；精確提交並保留工作區，不push。刪本計畫scratch前先整理rulings／deferred至文件及最後回覆。

Self-review：Task1資料契約供Task2表單與Task3投影；Task3 IDB升級同時改兩個opener及harness避免VersionError。Task4驗證前三項實際組合；公開首頁不解析Cookie，不為跨裝置方便而改私人邊界。使用者已要求在本對話續作並沿用授權，不重複核准。
