# 公務公告持續收錄 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 從單一指定管理者Gmail只發現官方MailView網址，匿名驗證後持續新增公開公務公告，並能安全接續回補／重試。

**Architecture:** Gmail讀取及私有候選由現有Render應用處理；公開公告仍沿用既有office_mail來源／版本。GitHub每小時排程只觸發固定受保護端點，不取得Gmail token或私人DB權限。私有進度、讀信租約與公開發布交易各自短暫、身分綁定、可重試。

**Tech Stack:** Python、FastAPI、SQLAlchemy、Alembic、既有Gmail SDK／TokenService、PostgreSQL／SQLite、Jinja、pytest、Node。

**Spec:** docs/superpowers/specs/2026-11-05-office-discovery-design.md（2026-11-05使用者已確認）。

**Execution:** 保留本對話由主代理實作的偏好，不重新詢問執行方式。現有由App管理的detached worktree保留，原OneDrive工作區不動。此計畫先供審閱，審閱後依序實作；不是功能已完成宣告。

## Global Constraints

- 只綁定明確指定的Google subject；一般使用者不自動成為公開來源。預設關閉；缺少有效提供者／觸發Secret不能啟用。
- 固定from:mailoffice@nkust.edu.tw，核對實際From；初次14天、固定UTC epoch時間窗、之後重疊24小時；每頁10封、每次最多20封、工作預算60秒、每次最多發布3個候選。
- 只接受normalize_office_url既有精確MailView網址，禁止ID掃描／任意來源／一般附件。正文、主旨、收件者、Gmail ID及憑證不進公開表、HTML或Actions。
- 沿用gmail.readonly、加密token、UserSyncLease與office SourceLease；不新增服務、付費、OAuth範圍、推播或其他寄件者。
- 新增0010私有進度／候選表；不修改正式DB、設定Secret或啟用真實讀信，直到可審閱驗收結果備妥、提供者選定與正式啟用步驟完成。觸發憑證若由瀏覽器設定，由使用者本人輸入／提交。
- 既有公開同步角色無新私有表權限；GitHub不獲得私人DB_URL、Gmail token或解密金鑰。
- 完整掃完才更新「最後完整檢查」；回補未完不能假報全部完成。重讀成功不掩蓋新信發現失敗。
- OAuth Testing可能7天失效；不更改Production／驗證或承諾無限期無人維護。第一段只解來源持續性及必要狀態，整站其他四組缺口保留於site-completion-audit，不偷偷擴大本計畫。

## Review Focus

- 一頁中途失敗／預算用完，重啟後不得跳過該頁未處理郵件；Task2/3驗證重讀與去重。
- 公開寫入成功但私有候選標記失敗，下一輪不能複製公告或遺失待處理項；Task3驗證兩步中斷。
- 提供者刪除後相同整數user ID被重用、授權刷新或租約替換，舊工作不能替新帳號讀寫；Task1/3驗證固定subject與fence。
- Gmail頁面token重複／失效、同秒邊界及分頁超額，不能宣稱全收錄；Task2/3驗證固定窗恢復與待處理狀態。
- 新信發現已失敗而舊公告重讀仍成功，公開頁不能只顯示綠色最新時間；Task4/5驗證獨立彙總、不讀私有表。

## 檔案分工與共用介面

新增app/models/office_discovery.py、alembic/versions/0010_office_discovery.py：僅私有schema。新增app/core/office_discovery.py：設定與固定錯誤；app/database/office_discovery.py：身分綁定進度／候選與工作租約；app/services/office_mail_discovery_source.py：只擷取網址；app/services/office_mail_discovery.py：有界工作；app/api/office_discovery.py：內部觸發與管理者頁面；app/templates/web/office_discovery_settings.html：管理狀態。既有office_mail來源與公開同步服務保持職責，不把Gmail讀取塞進office_mail_sync。

### Task 1: 私有schema、設定及進度交易

**Files:** Create上述models/core/database與0010；Modify alembic/env.py、app/database/schema.py；Test tests/test_office_discovery_state.py、tests/test_multi_user_database.py、tests/test_public_sync_permissions.py。

**Interfaces:** DiscoverySettings(enabled:bool=False,owner_sub:str='',trigger_secret:str='')（secret repr=False）；load()讀NKUST_OFFICE_DISCOVERY_ENABLED、NKUST_OFFICE_DISCOVERY_OWNER_SUB、NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET，啟用時subject非空、Secret至少32個ASCII字元，非法設定fail closed。DiscoveryRepository(database,owner:CurrentUser)；acquire(now)->owner_token、fence(session,token,now)、release(token)、state()->dict、commit_page(token,*,window_start,window_end,page_token,urls,complete,now)、due_candidates(token,now,limit=3)->list、mark_candidate(token,url,*,status,error_code=None,next_retry_at=None,now)。後續只使用這組介面。

- [x] Step1：建立RED測試：upgrade0009→0010保留公開／私人既有資料；User刪除CASCADE私有state/candidate、公開公告仍在；userid與subject不符拒絕。候選(user_id,url)唯一；私有狀態enum檢查；Secret不出repr／錯誤；enabled且缺Secret／subject拒絕。兩個並行acquire僅一個成功、冷卻300秒、租約120秒可fence續期、過期舊token拒寫。
- [x] Step2：跑pytest tests/test_office_discovery_state.py -q，確認缺介面RED；測試用合成帳號與URL。
- [x] Step3：實作兩表。State含user_id FK、google_user_id、固定窗開始／結束、page_token、完整掃描時間、run lease owner/expires、next_allowed_at、last_status/error_code；Candidate含user_id FK、canonical_url、發現時間、pending/retry/published/rejected、attempts/next_retry_at、安全error_code。所有網路之外短交易先比對User固定subject再fence，同現有鎖順序。每頁urls與游標同交易保存；不存郵件正文／主旨／訊息ID。更新REQUIRED_REVISION=0010與既有schema gate測試期望；不要寫死測試假裝新schema等於0009。
- [x] Step4：在SQLite及獨立PG跑schema／並行／受限公開角色測試；公開角色對兩張新表SELECT/INSERT/UPDATE全部失敗，既有公開同步仍成功。不使用正式庫驗證。
- [x] Step5：提交 feat: persist private office discovery progress and candidates。

### Task 2: 有界Gmail頁面及網址發現

**Files:** Create app/services/office_mail_discovery_source.py；Modify app/services/user_gmail_service.py（只新增發現用方法）；Test tests/test_office_discovery_source.py、tests/test_user_gmail_service.py、tests/test_email_parser.py。

**Interfaces:** extract_office_urls(email:DecodedEmail)->tuple[str,...]；discovery_query(start:datetime,end:datetime)->str；UserGmailService.list_discovery_page(start,end,*,page_token=None)->tuple[tuple[str,...],str|None]；UserGmailFactory.discovery(user:CurrentUser,*,timeout_seconds:int)->UserGmailService，這個專用client使用num_retries=0、1..10秒socket timeout，不改一般同步client的重試契約。每個client單次工作獨享並close。

- [x] Step1：RED：實際From不是mailoffice（即使顯示名稱像校方）回空tuple；HTML href與純文字合法MailView多筆去重、:443正規化；拒絕http/query/fragment/他站/userinfo/腳本URL、偽文字連結不取得任意host；PRIVATE正文marker不出抽取結果。query固定sender、includeSpamTrash=False、maxResults=10、after/before為UTC epoch秒；回傳ID型別／重複ID／token長度錯誤拒絕。
- [x] Step2：跑pytest tests/test_office_discovery_source.py -q確認RED。測試API替身不得連真實Gmail。
- [x] Step3：實作本文暫存記憶體→網址tuple；沿用DecodedEmail／MIME2MiB、32層、200parts，只允許無檔名的正文部分；不下載一般附件、不持久保存郵件副本。專用factory用現有TokenService與subject綁定取得授權，不讀token.json；發現client不改現有UserGmailFactory.__call__行為。
- [x] Step4：測試錯誤授權映射GMAIL_REAUTHORIZE／credentials unavailable、MIME超量／惡意編碼／附件、client關閉、0次SDK重試；跑新來源、既有user Gmail與parser測試全通過。
- [x] Step5：提交 feat: discover canonical office URLs from bounded owner mail reads。

### Task 3: 可接續掃描、匿名發布與彙總

**Files:** Create app/services/office_mail_discovery.py；Modify app/database/office_discovery.py、app/services/office_mail_views.py；Test tests/test_office_discovery.py、tests/test_office_mail_sync.py、tests/test_postgresql.py。

**Interfaces:** run_office_discovery(database,settings:DiscoverySettings,gmail_factory,*,now=None,monotonic=None,public_source=None)->DiscoveryResult；DiscoveryResult.to_public_dict()只回status/scanned/discovered/published/rejected/pending/error_code（數字非bool非負，狀態success/partial/failed/busy）。Task4調用此函式；私有管理頁另透過repo取得安全細節。scanned為本次完成處理封數、discovered為本次新建唯一候選數、published只計本次真正新增公開篇數（既有URL可標published但不膨脹此數字）、rejected為本次拒絕數、pending為仍待處理總數。

- [x] Step1：RED測試三封合成通知含兩個新官方URL→經匿名公開替身檢查added2；沒有URL／限制頁不發布；重複URL只一篇；合成PRIVATE marker在所有public表／to_public_dict中皆不存在。兩頁中途失敗保持該頁游標；回補超過20封保持incomplete；最後一頁完成才更新最後完整檢查。
- [x] Step2：跑pytest tests/test_office_discovery.py -q確認RED。
- [x] Step3：實作工作租約→UserSyncLease讀信（max20、page10、deadline60秒，開始每次I/O前預留剩餘socket預算）→同交易保存完整頁候選／游標→釋放UserSyncLease→有餘裕時最多3個候選匿名import_office_mail。公開階段與讀信階段不重疊持有UserSyncLease／SourceLease，工作租約保護整次狀態；網路不在DB交易內。剩餘少於15秒不開始公開讀取，留下pending，不宣稱已發布。
- [x] Step4：實作固定窗：首次now-14days至now，完成後新窗start=previous_end-24h，end=now；token失效重開同窗並依URL去重、重複token安全報錯。解析永久不支援郵件視安全略過，暫時Gmail/DB錯誤不推游標。候選網路／429／5xx按1h、6h、24h重試；登入／限制／404／結構拒絕標rejected，保留固定理由。公開成功但候選標記失敗下輪可重新導入，canonical去重；不吞DB錯誤假成功。
- [x] Step5：將純彙總寫入既有PublicSourceState/PublicSyncRun的獨立key nkust-office-discovery（不含owner/游標／候選URL）。S.last_success_at只代表完整窗掃完；S.history_status為not_started/incomplete/complete。R.status與error_code記安全整體狀態；不挪用公開公告的成功時間。公開view只讀此公開彙總及既有公開表，不SELECT新私有表；實際候選pending數只由內部回傳／管理頁顯示，不暴露私人queue。新增查詢隔離測試。
- [x] Step6：加入帳號刪除／ID重用、授權刷新衝突、工作租約過期、public lease busy、同秒重疊窗、頁token失效、公開成功後中斷、429/5xx及拒絕恢復測試；SQLite+獨立PG驗證，提交 feat: resume office discovery and publish anonymously verified notices。

### Task 4: 管理者操作、固定觸發與來源提示

**Files:** Create app/api/office_discovery.py、app/templates/web/office_discovery_settings.html、tests/test_office_discovery_api.py；Modify app/web.py、app/api/session.py、app/templates/web/account.html、office_mail_status.html、privacy.html、office_mail_list.html；Extend tests/test_office_mail_pages.py。

**Interfaces:** POST /internal/office-discovery/run：Authorization Bearer專用Secret，body為空、上限1024bytes、無任意query；disabled404、未授權401、過大413、非空參數422、冷卻429（Retry-After300）、忙碌409、授權失效安全503，其餘依DiscoveryResult；僅回補pending時200/partial＋OFFICE_DISCOVERY_PENDING，真正依賴故障回503/failed或partial，不能把兩者混為成功。GET /settings/office-discovery及POST /settings/office-discovery/run：必須固定owner current_page_user＋same-origin／CSRF；不使用觸發Secret替代一般帳號權限。普通帳號不得讀管理者狀態。

- [x] Step1：RED測試：未設定／無token／錯token／Cookie但無Bearer／任意account或URL參數不能觸發；正確token僅執行固定服務且回傳安全白名單。owner手動表單成功、非owner拒絕、CSRF失敗；設定頁不顯示token／Google subject。偽造X-Forwarded身份標頭不改owner。
- [x] Step2：跑pytest tests/test_office_discovery_api.py -q確認RED。
- [x] Step3：在create_app新增可注入discovery_settings供合成測試；lifespan建立服務且預設disabled。設定enabled才要求完整subject／Secret，預備檢查錯誤不部署。hmac.compare_digest比對Secret，錯誤不帶原例外／header；no-store回應、無CORS開放、觸發不中斷既有RSS／Gmail路由。使用現有safe identity/token流程取得指定user，不接受請求內subject。
- [x] Step4：管理頁顯示啟停、回補範圍、完整檢查時間、候選pending/retry/rejected彙總、需重新授權／繁忙／冷卻及手動執行結果。中文、手機、表單重試清楚；不外送通知、不讀其他帳號。新信發現的公開成功時間、回補狀態與既有重讀時間分列，未啟用時不宣稱新信自動更新；保留舊資料與安全提示。
- [x] Step5：公開入口標示「全部已收錄公務公告」，保留mode=all及既有URL，不影響校區局部更新。更新privacy，清楚區分管理者背景發現例外與普通使用者手動同步，私有游標／候選保存及帳號刪除；Testing7天限制只在管理介面說明。公務錯誤頁補進現有public error分類，返回連結仍指公務來源、5xx重試保留原條件。
- [x] Step6：測試新信發現failed＋office重讀success仍呈警示；所有公開GET只讀公共表、無私人marker；32既有公開頁與13前端檢查及新API測試通過，提交 feat: expose safe owner discovery controls and source freshness。

### Task 5: 排程整合、完整驗收與分段啟用

**Files:** Create scripts/trigger_office_discovery.py、tests/test_office_discovery_trigger.py、docs/office-discovery-validation-2026-11-05.md；Modify scripts/refresh_public_sources.py、tests/test_office_mail_workflow.py、README.md、docs/public-announcements.md；最後才更新main既有workflow。

**Interfaces:** trigger腳本固定HTTPS nkust-mail-assistant.onrender.com/internal/office-discovery/run，不接受任意host／轉址／query；從env讀新增觸發Secret（repr／log不輸出），timeout120秒、網路／5xx最多重試1次、409/429回安全busy不反覆喚醒、其他失敗exit1；200/partial且僅OFFICE_DISCOVERY_PENDING為可接續回補提示、exit0但摘要標未完成，任何其他partial不假報成功。沒有Secret表示尚未設定、明確skipped，不冒稱已成功掃信。已有Secret但錯誤／缺服務必須失敗。

- [x] Step1：建立RED：受控HTTP替身驗證正確POST／header／空body、錯URL不傳憑證、redirect不跟隨、timeout有界、401/503安全失敗、429/busy提示、回傳型別／負數／bool／多餘私有欄位拒絕且不打印正文；fake CLI整合驗證先前三來源失敗仍呼叫discovery。保留既有有效article partial警告語義，不覆蓋main較新workflow內容。
- [ ] Step2：實作trigger與runner獨立階段（完整argv、無shell），workflow只新增專用觸發Secret env，不碰現有公開DB Secret。步驟摘要分開列發現、公開發布、RSS及文章結果，CLI呼叫不得洩漏header或郵件資料。摘要文字分清office-refresh只重讀、discovery才找新信，不再對整個workflow寫「不會發現新公告」。跑新trigger、既有workflow測試及13Node檢查。
- [x] Step3：全新臨時PG跑完整pytest（目前基線679、0略過不是新功能通過），含私有表權限、併發、帳號隔離、migration及中斷恢復；diff檢查。以合成Gmail完整驗收至少新增兩篇而非只重讀原1篇；手機公開列表／設定狀態／錯誤／重試，原校區原地更新不退步。安排一次獨立整段review，重要問題RED→GREEN修正後相關完整驗證。
- [ ] Step4：備妥0010相容回復版本並測試關閉flag仍能閱讀公告／私人既有資料；記錄正式schema0009→0010備份、遷移、失敗回復步驟。正式schema切換安排維護視窗並暫停觸發；程式先保持本機／候選分支，不讓依賴0010的新CLI提前進入仍為0009的排程。與使用者核對將綁定的實際Google帳號，不從聯絡Email猜。正式新Secret設定屬擴充安全存取，依當時工具規則由本人確認／輸入；在這些啟用條件完成前，只交付可審閱本機成果，不用等待授權來省略前述實作與驗收。
- [ ] Step5：只在具體啟用條件完成後，依既有部署流程推送／Render手動發布；先確認schema與flag關閉健康，再設定單一owner與triggerSecret、啟用功能。首次手動小批工作確認新增／拒絕／pending、原文來自匿名官方頁、日誌無私人marker；未驗證不能宣稱已自動收錄。再更新workflow並手動執行，後續實際觀察至少一次cron，分別記錄證據。
- [ ] Step6：更新驗收文件：產品／workflow SHA、migration／備份／相容回復、提供者不公開、真實與合成驗證範圍、實際篇數及涵蓋窗、完整掃描與重讀時間、Testing重新授權限制；關閉臨時server／PG／管理分頁。整站其他缺口保持下一輪清單，不宣稱全站已完善。

## 計畫自審與裁定

Spec coverage：設定與兩私有表Task1；Gmail固定來源Task2；時間窗／持久候選／公開發布Task3；管理／公開狀態Task4；觸發／完整驗收／啟用／回復Task5。Review Focus五類各有明確測試。

Interfaces consistency：CurrentUser、DecodedEmail、OfficeSyncResult沿用原介面；Task3只接受Task1設定／repo與Task2專用factory，不偷用一般sync service。公開讀取只依既有公共state/run的彙總，不查私有候選。

Ruling：60秒是工作調度預算；各網路呼叫使用剩餘預算且SDK無自動重試，接近截止不啟動新項，實際冷啟動／token刷新時間須驗收，不能假稱硬即時完成。公開fetch仍沿用15秒既有邊界，不強行改成新的下載服務。

Ruling：公開pending數非必要公開資訊，保留在內部／owner狀態，不為它新增公開JSON欄位；公開頁仍顯示新信完整檢查／回補狀態及內容重讀。這避免私人候選間接洩漏，代價是一般學生只看到延遲狀態而非queue細節。

Ruling：本期只規劃來源管線及必要文字／狀態，私人摘要／移除行動卡／待辦銜接、全站局部搜尋另分段設計，避免未完成來源便全面重寫。
