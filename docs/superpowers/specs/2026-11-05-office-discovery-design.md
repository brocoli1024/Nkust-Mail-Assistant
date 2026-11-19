# 管理者Gmail發現公開公務公告網址：具體設計

日期2026-11-05。狀態：使用者2026-11-05已確認可接受；進入實作計畫，尚未實作／啟用。使用者已允許先提出此方式的具體設計，並未因此啟用背景讀信、設定新憑證或修改正式schema。本設計作為整站完善的第一段；整站盤點見../../site-completion-audit-2026-11-05.md。

## 1. 成功標準

一般學生免登入取得持續新增的、通過公開範圍檢查的公務公告；設定多校區後原地優先排序，仍可查看全部已收錄資料。管理者提供網址發現來源，不公開管理者郵件。公告重點、日期依據、原文及版本沿用既有服務。

公開區只保存匿名官方頁重新取得的內容；信箱原文、寄收件者、主旨、Gmail訊息ID、收到時間、token不能流入公開表、HTML、Actions日誌或摘要服務。私人收件範圍不是全校公告全集，不能承諾全校完整。

## 2. 三種方式與選擇

A（建議）：現有Render網站處理指定帳號，既有GitHub每小時排程只呼叫受保護的固定觸發端點。Gmail憑證仍由現有TokenService加密保存，Actions沒有私人資料庫權限或Gmail token；不新增服務或付費方案。代價是新增最小觸發憑證、私有進度／候選表與重新授權維護。

B：把管理者Gmail refresh token及必要設定放到Actions，讓runner直接讀信。可在網站休眠時處理，但擴大憑證分布，與既有私人token管理重複，故不採用。

C：只在管理者登入後按同步時發現網址，不新增排程觸發憑證。維護簡單，但無人開站時不能持續找新公告；保留為手動回退，不能宣稱符合定時收錄目標。

## 3. 指定帳號與授權

新增預設關閉的office discovery設定；管理者須明確指定本站既有帳號，以Google固定subject綁定，不以可變Email或「第一位登入者」判定。設定只影響這個帳號；一般使用者的Gmail同步不得偷偷貢獻公開來源。

沿用UserGmailFactory、TokenService及UserSyncLease；不使用Desktop token.json，不要求Gmail密碼，不新增OAuth scope。既有gmail.readonly足以使用寄件者／時間條件查詢；但它在OAuth層級仍是整個信箱唯讀權限，查詢限制由本站程式落實，不能宣稱Google已把權限縮到單一寄件者。[Gmail查詢](https://developers.google.com/workspace/gmail/api/guides/filtering)、[messages.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)

帳號被刪除、授權撤銷或Google身分變更立即停止；不改用別人的憑證。既有公開官方公告保留，私有進度與候選隨指定帳號資料刪除。變更提供者須清空／重建該提供者的私有進度，不沿用另一帳號的訊息參照。

## 4. 發現流程及初次範圍

固定查詢from:mailoffice@nkust.edu.tw，初次回補最近14天，不含垃圾桶／垃圾郵件。再以實際From解析結果核對固定地址，顯示名稱不能冒充寄件者。只讀符合查詢的郵件本文與HTML以尋找連結，MIME大小／深度沿用既有限制，不下載一般附件；需附件才能找到資訊者列不支援，不公開郵件替代。

只抽出精確HTTPS officemail.nkust.edu.tw/Mail/MailView/正整數。沿用normalize_office_url，拒絕userinfo、query、fragment、其他host、流水號掃描及不可信重新導向。重複URL去重，From本身不作公開資格依據。

以固定UTC秒數時間窗分頁，下一窗重疊24小時，避免日期時區與新到信造成邊界遺漏；郵件到達順序不當官方發布時間。Gmail日期字串預設以PST解讀，因此使用epoch秒數而非台灣日期字串。每次最多讀20封（每頁10封）、整體60秒工作預算；初次未掃完顯示「回補中」。只有一頁郵件皆完成候選持久保存或安全拒絕，才移動該頁游標；進程中斷重讀該頁，URL去重防重複。分頁token失效重開同一固定窗，不直接跳到最新。完整掃完才更新該窗完成時間。

郵件無官方網址就略過，不能把原始信件或附件變公開文章；一般使用者不需連Gmail也能閱讀已發布公告。

## 5. 私有進度、候選與公開檢查

規劃兩張最小私有表：office_discovery_state（指定user/Google subject、固定時間窗、分頁token、最後完整掃描、執行租約／冷卻、狀態與固定錯誤碼）；office_discovery_candidates（指定user、規範URL、發現時間、狀態pending/retry/published/rejected、attempts、next_retry_at、固定錯誤碼）。不保存郵件正文、主旨、收件者或原始HTML。游標屬私人操作資料，不放公開來源metadata。

候選表user＋canonical_url唯一。新公告與失敗項有持久待處理狀態，不能只有記憶體佇列；這是新增私有表的理由。無私人表讀取授權給nkust_public_sync。預期新增0010 migration，保留既有表與資料，不做刪除或降級；正式套用前另行核對備份及授權。

讀信租約先取得並在短交易中檢查身分；網路在交易外，候選寫入前再次fence，完成後釋放。公開發布階段再取既有nkust-office-mail SourceLease，不同時持有兩種lease，避免跨順序死鎖；公開寫入與候選標記用可重試的兩步，若中斷，現有canonical URL去重使再次發布不新增重複文章。

從候選匿名呼叫fetch_office_mail，使用既有公開結構／廣泛受文者／限制字樣／大小／TLS／IP／轉址邊界。登入、個別收件、限制或結構不符皆不發布，不因網址可打開就直接接受所有內容。404等持續性問題保留拒絕原因，429／5xx／網路失敗依1小時、6小時、24小時重試，仍受每次預算限制。安全拒絕不自動改解析規則，管理者可核對原因。

每次最多發布3個候選、僅在剩餘預算足夠時開始下一項；未處理項留下次。公告更新與版本沿用import_office_mail；公開標題、正文、發布日期、單位及重點全部取自官方頁，不取郵件收到時間或私人內文。既有office-refresh持續獨立運作。

## 6. 排程觸發與狀態

新增固定POST /internal/office-discovery/run；只接受專用觸發憑證，不能靠一般登入Cookie授權，無帳號／任意查詢／任意URL參數。伺服器端固定提供者、寄件者、時間窗與批次上限。請求大小上限1KiB，constant-time比對憑證，不放query，不寫日誌；未設定時端點不可啟用。每個提供者最多5分鐘執行一次且租約互斥。

一個新的最小觸發Secret分別由Render環境與GitHub Actions加密保存；只具啟動這個固定工作的能力，不提供私人查詢或任意資料庫操作。新增憑證設定屬啟用時需明確處理的存取變更；不把Gmail refresh token或正式管理員DB_URL傳給Actions。

沿用每小時17分workflow，加入此獨立階段；RSS／本文／已知公務重讀失敗不阻止發現工作，任何程式錯誤不能假報全成功。每次HTTP完成有界批次才回傳，避免在Render Free用不持久的背景工作假裝已處理。冷啟動允許較長客戶端等待，單次觸發超時可重試，持久游標與去重確保安全；確切超時設定須在預備／正式手動執行驗收。

回傳只含scanned/discovered/published/rejected/pending及安全錯誤碼，不含Gmail ID、地址、主旨、原文或token。管理者可在自己的設定頁手動執行同一受身分／CSRF保護的工作並查看詳細安全狀態；其他帳號不能進入。未完成回補是pending，不是全部完成。授權失效是需重新連結，不自動改OAuth或反覆重試。

公開區分開顯示「新公告最後完整檢查」「已收錄內容最後成功重讀」「收錄篇數及涵蓋日期」。只公開彙總，提供者身分與私人游標不顯示。來源失敗時保留舊文章並說明新公告可能延遲，避免用重讀成功掩蓋讀信失敗。

## 7. OAuth及長期運作限制

現有專案仍為Testing。Google說明外部Testing且使用非基本身分範圍時，refresh token通常7天到期；Gmail readonly不屬基本身分範圍。[Google refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)

因此首版可驗證每小時執行，但不能保證無限期免維護；管理者需在授權失效時重新連結。正式Production／驗證資格、必要審查及可能成本須另評估，不默默變更OAuth、購買服務或承諾立刻全面開放。此限制需於啟用前讓管理者接受，並在完成狀態中保留。

## 8. 實際修改範圍與驗收

新增有界的Gmail連結發現服務、私有候選／進度repository、觸發route與設定、0010 migration及管理者狀態頁；擴充UserGmailService的固定查詢／分頁讀取，不改一般使用者的固定寄件者同步契約。沿用office_mail_source/briefs/sync/views及既有公開表；新增彙總狀態查詢，不把私有候選直接join到公開頁。

更新workflow、privacy／資料保存／收錄說明。整站其他閱讀與待辦改善分別實作，不讓一個來源改動重寫全站。

必要驗收包括：

- 假Gmail三封通知找出多個新URL，匿名官方頁檢查後公開筆數增加；無URL、私信、偽顯示名稱、個別受文者、登入頁、限制頁不公開。所有公開表／HTML／日誌查不到合成私人marker。
- 多頁、同秒邊界、重疊窗、token失效、中斷前後、同URL多信、回補未完不跳游標；處理每頁未完成時可重讀且不漏項。
- 所有者切換／刪除／Google subject不符／其他帳號／觸發未授權／過大輸入／錯誤參數／重放冷卻、並行及租約過期；私有候選與token永不開放給公開同步角色。
- 公開校區排序、摘要、原文與版本正常，重試不重複公告；日期仍可核對、無法確定不匯出；原有私人同步及帳號隔離不退步。
- 獨立PostgreSQL全套、前端檢查、手機與實際故障恢復。正式先手動有界執行，核對新增篇數、來源與最後完整掃描，再實際確認排程。沒有觀察到的cron不宣稱已執行。

## 9. 分段啟用與回復

先用合成Gmail／匿名官方頁替身實作與驗收，再備妥可回復的0010相容版本；正式schema、提供者及觸發Secret需在審閱具體結果後啟用。不在本次設計階段讀真實管理者Gmail或設定任何Secret。

部署前備份，migration只新增私有表。停用時先關discovery flag／觸發入口及Actions步驟，保留現有公開公告和私有進度供核對。回復應用需使用已通過0010 schema gate的相容版本，不能假定舊0009產品可直接啟動，也不刪新表來強行降級。

## 自審

已明列三種選擇、推薦方案、憑證邊界、新schema及回復限制。發現、候選、公開重讀、首次回補、普通私人同步皆分開。沒有全校完整保證、無限期Testing token保證、真假資料混用或授權已啟用宣稱。指定帳號與正式憑證值由啟用前明確選定，不使用猜測的Email或既有聯絡地址作授權。
