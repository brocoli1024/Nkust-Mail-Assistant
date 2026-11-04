# 公務公告校區優先與重點整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 建立免登入公務公告入口，以裝置多校區偏好優先排序，依內容整理重點並保留官方原文依據。

**Architecture:** 新來源nkust-office-mail與既有nkust-latest並列，使用既有公開表、來源lease與版本保存；匿名頁面不解析登入者或私人表。管理者導入已確認網址，排程僅重讀既有公告；校區偏好只在瀏覽器保存，伺服器依此次GET條件在分頁前排序。內容整理採可驗證的分區與類型規則，不新增AI外傳或推播。

**Tech Stack:** Python、FastAPI、Jinja2、SQLAlchemy、既有PostgreSQL／SQLite、BeautifulSoup、原生JavaScript、pytest、Node契約檢查。

**Spec:** docs/superpowers/specs/2026-11-04-office-mail-campus-design.md（使用者2026-11-04已確認）。

**Execution:** 沿用本對話由主代理逐段實作的偏好，採executing-plans；每段保存驗證結果，結束後獨立程式審查。不建立新對話或改用未經選擇的執行方式。本計畫待使用者審閱確認後開始產品實作。

## Global Constraints

- 使用source_key=nkust-office-mail隔離，沿用public_announcements、public_source_states、public_sync_runs、public_source_versions，不新增跨私人外鍵或公開Gmail快照。
- 只接受HTTPS officemail.nkust.edu.tw/Mail/MailView/正整數，不接受帳密、任意query、片段、其他路徑／網域或流水號掃描。
- 本期不擴充一般私人Gmail寄件者、不讀取其他帳號、不增加裝置推播、通知授權、位置定位、付費服務、OAuth範圍或新外部AI傳送。
- 選項為建工、第一、楠梓、燕巢、旗津，允許多選；「跨校區／不固定」代表不設定偏好，不是第六個地理校區。
- 排序在資料庫分頁之前完成，不能只把當頁20篇重新排序。
- 定期office-refresh只重讀已導入的公告，不能宣稱能自動發現所有新公務郵件。
- 既有分類／對象選單變更立即跳轉行為不變。
- 公務詳情只顯示重點、來源與完整原文，不顯示公告行動資訊卡。
- 628項為實作前最後完整測試基線，不能當作本功能已通過。沒有正式資料導入、排程或部署成功證據前，不改文件宣稱已上線。

## Review Focus

- 公開200頁其實是登入／錯誤頁或包含私人收件人：Task 1測試拒絕並保持原資料。
- 校區只出現在寄件單位地址／受文者，不是影響範圍：Task 2測試不誤標；Task 4未知組仍可見。
- 原文的班別／福利／否定資格在不同段落：Task 2測試完整整理，不因三點上限截去後文。
- 偏好存在但URL明確選全部，或儲存損壞／被封鎖：Task 4測試尊重URL與可恢復錯誤，不改成空白清單。
- 已有RSS與私人版本在新網址識別擴充後被錯誤共用或漏讀：Task 3／5測試來源、帳號與歷史隔離。

## 檔案與介面分工

新增app/services/office_mail_source.py負責匿名來源；office_mail_briefs.py負責純函式整理；office_mail_sync.py負責公開寫入；office_mail_views.py負責有界列表／詳情／歷史查詢；app/api/office_mail.py負責GET路由。新增office_mail_list.html、office_mail_detail.html、office_mail_preferences.html、office_mail_brief.html與office-mail-preferences.js、office-mail-reading.js。只針對功能擴充public_sync.py、source_history.py、public_cli.py、web.py、site_header.html及account.css，不重構既有RSS／私人控制器。

### Task 1: 有界官方公務公告來源

**Files:** Create app/services/office_mail_source.py; Test tests/test_office_mail_source.py。

**Interfaces:** Produces OFFICE_SOURCE_KEY='nkust-office-mail'、normalize_office_url(value:str)->str、OfficeDocument(url:str,external_id:str,title:str,body:str,department:str,published_at:datetime|None)、parse_office_mail(data:bytes,url:str)->OfficeDocument、fetch_office_mail(url:str,*,transport=None)->OfficeDocument。失敗使用PublicSourceError的固定安全代碼，不輸出例外原文。

- [x] Step 1: 新增失敗測試：69929形式URL可正規化、external_id='69929'；http／userinfo／query／fragment／其他host／非正整數拒絕且不發出請求。合成頁解析必須保留正文段落與小標，排除轉寄UI、script、form與聯絡頁尾；發布日期不明保持None。
- [x] Step 2: 跑pytest tests/test_office_mail_source.py -q，確認因缺少介面／行為而失敗。
- [x] Step 3: 實作以上介面。沿用MAX_BYTES=2MiB與_pinned下載邊界，單次總deadline=15秒、最多4次同一規範URL重新導向，正文上限40000字。只提取明確公務主旨／說明結構；登入、限制、404、錯誤頁、缺正文或私人收件資訊拒絕。發布日期只用公告頁日期，不用收件或HTTP時間。
- [x] Step 4: 加入200登入頁、403、404、200限制頁、私人email／個人收件人、超大／非UTF8、重新導向私人IP／他站、正文HTML跳脫等測試；以受控transport驗證無Cookie／Authorization及無附件讀取。跑來源測試與既有tests/test_public_source.py、tests/test_linked_registration.py，要求全通過。
- [x] Step 5: 提交來源與測試：feat: add bounded public office mail source reader。記錄哪些真實頁面已實讀，不將合成資料當正式收錄。

### Task 2: 校區判定與依內容整理重點

**Files:** Create app/services/office_mail_briefs.py; Test tests/test_office_mail_briefs.py。

**Interfaces:** Consumes OfficeDocument。Produces CAMPUS_LABELS（固定順序jiangong=建工、first=第一、nanzih=楠梓、yanchao=燕巢、qijin=旗津）、parse_campuses(values:list[str])->tuple[str,...]、build_office_brief(doc:OfficeDocument)->dict。brief結構為version='office-brief-v1'、kind（works/training/general）、headline、campus_flags（五個boolean）、campus_global:boolean、campus_evidence:list、sections:list、warnings:list；section包含label、items，每個item含text和evidence:list；evidence固定為quote、start、end，均指向doc.body。每次整理只使用該篇doc，不接受其他公告或私人資料。

- [x] Step 1: 先寫測試：五校區可多選、代碼去重按固定順序、非法代碼拒絕；全校施工正文可標global；簽名中的「建工校區地址」與受文者全校學生不能當影響校區。每個quote必須滿足doc.body[start:end]==quote。
- [x] Step 2: 跑pytest tests/test_office_mail_briefs.py -q並確認RED。
- [x] Step 3: 實作主旨清理、段落／小標分組與類型整理。施工區分地點、影響期間、封閉範圍、替代動線，保持校區—時段成對。培訓列出全部班別、各別課程時程、福利與條件、資格及例外。一般公告沿原有小標整理；無可靠結構時明確提示限制，不以前三句當完成語意摘要。不產生沒有原文依據的結論。
- [x] Step 4: 加入合成三班別／四項福利、跨段落退費條件、最高獎勵限制、長句末尾「學生不得報名」、多校區不同施工時段、附件才有資料、資格矛盾、未知校區與標題／正文衝突測試。沒有明列替代動線不得自行補造；不將公告日期或課程日期當截止。完整段落只保留一次證據，不截斷重要限制。
- [x] Step 5: 測試通過後提交：feat: structure office mail campus and content briefs。69929作為瀏覽器實際驗收案例，原文只存忽略的本機驗收快取；提交的測試用合成班別與合成資料。

### Task 3: 來源隔離、版本、導入與重讀CLI

**Files:** Create app/services/office_mail_sync.py; Modify app/services/public_sync.py、app/services/source_history.py、app/public_cli.py; Test tests/test_office_mail_sync.py、tests/test_public_sync_permissions.py、tests/test_public_cli.py、tests/test_source_history.py。

**Interfaces:** SourceLease(database,*,now=None,source_key=SOURCE_KEY)明確只接受nkust-latest或nkust-office-mail，所有acquire／verify／release都用同一實例key。public_snapshot與record_public_version新增可選office參數，保存Task 2 brief及固定fetch_error，預設舊RSS行為不變。official_identity只新增精確合法MailView分支，其他規則不放寬。Produces import_office_mail(database,urls:list[str],*,source=fetch_office_mail,now=None)->OfficeSyncResult、refresh_office_mail(database,*,limit=8,source=fetch_office_mail,now=None)->OfficeSyncResult；結果包含added、updated、unchanged、failed、status、failures（只含公開ID／固定代碼）。

- [x] Step 1: 建立RED：導入合成來源新增1筆，重複官方ID不重複，同標題不同ID不合併，正文變更保存新版本；另來源的lease不互相冒用。角色無私人讀取／DELETE／DDL權限仍可導入與重讀公務公告。
- [x] Step 2: 跑pytest tests/test_office_mail_sync.py tests/test_public_sync_permissions.py -q，確認新行為失敗；PostgreSQL權限測試需使用獨立受限角色，不能以略過視為通過。
- [x] Step 3: 實作有界批次、規範URL查找、P.excerpt保存清理正文，來源與分類／brief版本依據留在公開快照metadata.office。只在持有對應lease的短交易寫入，網路讀取在交易外，每篇失敗保留舊正文／brief並標記來源狀態，校區／摘要不能因失敗變成空值。同內容重讀只更新觀察／來源成功狀態，不製造假的官方內容變更。
- [x] Step 4: CLI新增office-import --urls-file PATH（UTF8每行一URL，忽略空白，最多20個不同網址，先全量驗證URL再發出請求）及office-refresh --limit 1..20（預設8，只處理既有nkust-office-mail）。不查Gmail、不讀管理者OAuth、無ID遞增掃描。測試部分失敗exit1、安全輸出、回收連線、限制數量、無效清單不部分導入、失敗後恢復、併發lease與原RSS預設均正確。
- [x] Step 5: 在獨立PostgreSQL及SQLite跑新同步／CLI、既有RSS／文章與來源歷史測試，再提交：feat: persist and refresh isolated public office mail。若發現既有公開角色無法使用現有表，停下回報具體缺權，不增加私人權限或修改正式庫。

### Task 4: 匿名頁面、裝置偏好與分頁前排序

**Files:** Create app/services/office_mail_views.py、app/api/office_mail.py、app/templates/web/office_mail_list.html、office_mail_detail.html、office_mail_preferences.html、office_mail_brief.html、app/static/web/office-mail-preferences.js、office-mail-reading.js; Modify app/web.py、app/templates/web/site_header.html、app/static/web/account.css; Test tests/test_office_mail_pages.py、tests/office_mail_preferences_check.cjs、tests/office_mail_reading_check.cjs。

**Interfaces:** list_office_mail(database,*,q='',category='',campuses=(),mode='all',page_number=1)->dict、office_mail_detail(database,pid:int)->dict、office_mail_history(database,pid:int,*,page_number=1)->dict。GET路由/public/office-mail、/public/office-mail/{pid}、/public/office-mail/{pid}/history。query為q（最多200字）、category（既有分類）、重複campus參數（最多5）、mode=all|priority、page（1..1000000），一頁20篇；路由驗證不接受任意return URL。偏好key為nkust-office-campus-v1，value={version:1,campuses:[合法代碼],skipped:boolean}。

- [x] Step 1: 建立RED：超過20篇且相關公告最舊時仍排進第1頁；相關與global同組、unknown次組、其他末組，各組以published_at DESC NULLS LAST,id DESC穩定排序，筆數與跨頁ID無遺漏／重複。mode=all或未選校區時按日期，不把未知／其他藏掉。
- [x] Step 2: 跑pytest tests/test_office_mail_pages.py -q及兩個新Node檢查並確認RED。
- [x] Step 3: 實作latest公開版本子查詢一次join。用metadata.office.campus_flags五個boolean與campus_global構成SQL CASE排序，再offset／limit；SQLite與PostgreSQL皆驗證。缺brief的合法舊記錄列unknown，不能直接以body LIKE校區名取代判定。GET不抓外部來源、不寫資料、不解析私人Session；查詢和頁面只允許此source。
- [x] Step 4: 實作多選面板、完成設定／稍後設定／清除／重試、全部與優先模式、來源成功時間／範圍／異常、真實空白與錯誤狀態。載入偏好時只在URL未明確給定校區或模式時恢復，避免反覆跳轉；按完成回第1頁並保留q／category，不再要求按搜尋。損壞儲存可提示並重選；儲存封鎖仍可用此次URL套用。無JS保留完整GET表單。不得使用Notifications API、service worker push或地理定位。
- [x] Step 5: 詳情先主旨與分區重點；依據、完整原文及歷史可展開；不輸出公告行動卡／個人修正表單／私人待辦資料。返回清單保留全部條件與錨點，讀取位置記錄只含path/id/y/at並限定本清單與TTL30分鐘。導覽新增公務公告，不把其他來源改名；手機導覽允許換行，320px不能水平溢出。
- [x] Step 6: 測試匿名不觸及私人表、私人標記／其他來源ID不可讀、HTML跳脫、no-store、GET無寫入、搜尋字元跳脫、頁碼／分類／campus非法422、全部模式尊重明確URL、偏好clear／skip／損壞／QuotaError／重試、返回／重新載入不迴圈。確認既有即時分類選單測試不退步後提交：feat: add anonymous campus-prioritized office mail pages。

### Task 5: 完整驗收、部署與收錄限制紀錄

**Files:** Modify README.md、docs/public-announcements.md、docs/release-2026-11-01.md; Create docs/office-mail-campus-validation-2026-11-04.md；規劃更新main的.github/workflows/public-announcements.yml（只在本機功能驗證後，且使用獨立workflow checkout，不改原工作區）。

**Interfaces:** Consumes Tasks 1–4及既有公開受限DB secret。部署仍為codex/web-deployment、schema 0009、Render Free；沿用既有正式上線授權。若實作發現需要變更schema、權限、OAuth、憑證或費用，先報告差異，不默默修改。

- [x] Step 1: 在全新臨時PostgreSQL啟動完整pytest，包含受限公開同步角色與私人隔離，要求0失敗；略過需逐項說明，不將SQLite代替PG併發驗收。跑所有tests/*_check.cjs及git diff --check。只有新增變更或未解疑慮才重跑。
- [x] Step 2: 用合成資料本機驗收320x780、390x844與桌面。複選建工／楠梓→完成立即套用→跨頁→詳情→返回→重新載入；全部模式不丟偏好；blocked storage有提示；鍵盤可操作面板、依據、原文。截圖標合成資料，正式頁不混入樣本。
- [x] Step 3: 只讀取得指定69929官方公開頁驗證三班別、全部福利／資格例外，確認重點實際可讀而非三句節錄。安全檢查URL／公開範圍後，由明確網址導入該篇作為第一筆正式公務資料；不讀管理者或使用者私人Gmail。其他網址需要管理者明確加入，頁面明示收錄限制。原文登入／限制就不導入並回報。
- [x] Step 4: 依requesting-code-review安排一次獨立程式審查；修正重要問題並驗證。確認分支差異只含範圍內改動，再push部署分支、手動Render部署，確認commit／Live／schema gate／匿名公務頁、來源標示及既有RSS正常。沒有實際成功就不宣稱已發布。
- [x] Step 5: 在既有workflow獨立checkout加入office-refresh --limit 8的獨立步驟，讓RSS／文章失敗不阻止此來源的已知公告重讀，來源工作互斥各用對應lease。先用本機受控CLI替身執行workflow run腳本，驗證一來源exit1時其他來源仍被呼叫且整體不假報全部成功，再發布workflow並手動驗收；不更改既有Secret或擴權。排程清楚標示只重讀既有公告，不是自動發現新公務信件。
- [x] Step 6: 完成驗收文件，分別記錄正式產品commit、workflow commit、導入ID與篇數、最新成功時間、真實／合成資料、已驗證與未驗證事項、摘要非生成式限制、回復至相容版本方式。關閉臨時DB／預覽server／管理分頁。最終交付一句成果、測試數與唯一下一步。

## 計畫自審

- Spec coverage：來源與隔離對應Tasks 1/3；校區判定／內容整理對應Task 2；設定、排序、返回、空白／錯誤對應Task 4；原文69929、限制、部署與排程對應Task 5。
- Interface consistency：OfficeDocument僅Task 1定義，brief格式僅Task 2定義；Task 3保存同格式，Task 4直接讀最新公開版本。SQL排序使用相同五個boolean與global，不建立前端第二套校區判定。
- Review focus五項皆在對應Task加入驗證。無任意URL抓取、私人Gmail匯入、額外推播／AI呼叫。沒有正式DB變更、費用或來源完整性承諾。
- Task 5 workflow腳本的受控CLI替身測試，執行時新增tests/test_office_mail_workflow.py與tests/fixtures/office_workflow_runner.py；只檢查實際呼叫與exit結果，不靠搜尋yaml字串認定正確。
- 此文件目前只決定實作與驗收方式，尚未執行上述產品工作；使用者確認計畫後在本對話進行。

執行完成2026-11-05：678項獨立PG、12項Node，產品b2d4cc6、workflow66756fb，正式導入與例行重讀均成功。實際／合成驗證邊界及保留限制見docs/office-mail-campus-validation-2026-11-04.md；儲存封鎖為Node受控驗證，非瀏覽器政策實測。
