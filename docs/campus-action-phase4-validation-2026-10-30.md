# 第四階段驗證紀錄（2026-10-30）

狀態：本機隔離工作區實作與驗證完成，未部署；正式環境不因本文件而視為已有。前階段基準53ec76f，本階段無新migration／schema／依賴／服務／OAuth／付費功能，REQUIRED_REVISION維持0008。沒有連正式資料庫或外部行事曆。

## 功能與界線

公開／私人／demo公告詳情及待辦匯出共用確認元件：活動或截止分開、日期／依據／來源可讀，只有supported/user_confirmed且勾選原文確認才產生檔案，pending/stale不直接匯出。原文時間尚未解析時需明確選方式；全天不含時間，定時自行核對後填Asia/Taipei開始與可選結束，不猜一小時。結束必須晚於開始。

payload僅最小標題／來源識別與安全連結、摘要／行動、兩日期狀態及有限依據節錄、current/snapshot；不帶整封私人原文／AI參考／帳號資料。私人頁不載入裝置儲存模組，不新增持久儲存或上傳。todo匯出加入時快照，不冒充目前公告。

修改選項、未保存修正、重設／刪除／重新讀取修正都取消舊確認；更新中及讀取失敗不繞回舊基準。下載不改公告／修正／待辦狀態。CLASS:PRIVATE僅提示不是加密，私人.ics需自行保護；示範檔名及內容明確標合成。

格式參照 [RFC5545](https://www.rfc-editor.org/rfc/rfc5545)：CRLF／75octet UTF-8安全折行、TEXT跳脫、全天DATE與翌日exclusive DTEND、定時UTC Z而非floating。時間經Intl Asia/Taipei解讀，不存在或不唯一時間拒絕；歷史轉換的負面測試依[IANA asia資料](https://data.iana.org/time-zones/tzdb/asia)。SHA256 UID依來源類別／來源識別／活動或截止穩定產生，不暴露私人來源識別；重複匯入行為由行事曆軟體決定。沒有邀請對象、組織者、自動鬧鈴或Calendar API寫入。

## 自動驗證

最小payload兩測試及ICS Node皆先缺模組RED→GREEN。頁面四測試先缺元件RED→57項相關頁面GREEN（21.14s）。包含private最小內容／XSS跳脫／owner隔離／GET不寫庫、待辦snapshot與新來源差別，以及public/demo免Session依賴。

ICS測試涵蓋分別日期、未確認／pending／stale拒絕、閏日／跨年／無效日期／四位年邊界、台灣午夜跨UTC日、可選結束與錯順序、DST不存在／重複時間、中文emoji折行及CRLF屬性注入、安全URL、UID穩定與種別分離、private/demo檔名內容、Crypto不可用。todo clock key測試確認每分鐘檢查但日期／狀態未變時不重繪，避免清空匯出選項。

首輪完整pytest506 passed、47 skipped、2 warnings、67.16秒；修正審查問題後最終完整pytest **506 passed、47 skipped、2 warnings、158.25秒（exit0）**，basetemp=data/audit-cache/phase4-review-final。六項Node檢查（ICS、calendar integration、todo store、action card store、filter、service worker）及diff --check皆exit0。兩項警告為既有測試客戶端棄用；47個skip為專用PostgreSQL未提供，不當成PG已驗收。

## 實際瀏覽器與下載檔

只使用loopback暫時SQLite／FakeGoogle與明確合成公告。先確認按鈕在未勾選／pending時停用、改選重設確認，demo日期修正後再次確認才可匯出。私人表單輸入未保存日期後，確認被清除且匯出停用。私人待辦標示加入時快照；正常登出A、合成B登入不見A待辦，私人頁沒有裝置store腳本。

已實際下載並讀取四個合成檔：

| 檔案 | 實際檢查 |
| --- | --- |
| nkust-public-event-2026-11-20.ics | DTSTART;VALUE=DATE:20261120、DTEND:20261121，1091bytes |
| nkust-public-deadline-2026-11-10.ics | 台灣00:30–01:30對應DTSTART:20261109T163000Z、DTEND:20261109T173000Z，1106bytes |
| nkust-demo-event-2026-11-20.ics | 合成示範標示、全天日期，1140bytes |
| nkust-private-event-2026-11-20.ics | CLASS:PRIVATE、僅合成A內容，無B內容，1092bytes |

四個檔案均UTF-8解碼、CRLF／行長／單一VEVENT／檔尾檢查通過。頁面只說「啟動下載，請確認下載清單；尚未驗證加入行事曆」，沒有落盤或匯入狀態保存。

公開／私人匯出元件320／390px無水平溢出，Tab焦點solid；phase4-calendar-mobile.jpg只含合成公告。未實測實體手機、其他瀏覽器、螢幕閱讀器、完全關JS；有noscript說明，原私人HTML操作不依賴此模組。未實測外部Google/Apple/Outlook匯入、去重與更新，不宣稱已加入。模組缺失／讀取失敗／async操作的降級以真實腳本VM測試驗證，沒有新增正式故障開關。

途中瀏覽器自動核准審查因額度不足拒絕了一次重試，當次操作未執行，沒有換工具繞過。額度狀態回復ordinaryUsageAllowed後，以同一瀏覽器工具恢復並完成上述四檔驗收。早期一次下載等待過長，後續設五秒事件／路徑檢查與工具總時間上限。

## 獨立審查與修正

一次fresh整範圍唯讀審查53ec76f..39aac07，報告因額度中斷後由同一reviewer憑原筆記完成，沒有重新審閱修正。原判0 Critical、2 Important、1 Minor。執行者依唯一時間契約將第三項歷史歧義納入Important處理；三項皆在同一輪RED→GREEN修正，沒有延期小項。

1. 重設／刪除／reread開始及失敗立即取消匯出確認；只有可信卡片paint後重新開放核對。integration腳本先重現reset仍可匯出，再通過async reset/erase及失敗reread。
2. Calendar核心載入失敗不再讓public todo清單拋錯／消失；檢查兩個選用模組並顯示降級文字，保留既有待辦操作。VM先重現未處理錯誤及零列，再通過。
3. 1895-12-31 23:55的台北六分鐘重複時間先重現未拒絕；改從附近實際offset建立候選，不限整小時轉換；新負面測試及既有DST／UTC案例通過。

## 裁定與審查保留範圍

| 項目 | 裁定與代價／限制 |
| --- | --- |
| 每分鐘重繪清空匯出表單 | 改為每分鐘檢查、僅台灣日期／稍後狀態改變時重繪；跨日或醒來仍可能清除確認，需重新核對。 |
| 外部匯入／重複項目 | 不呼叫外部行事曆，只交付檔案；匯入相容性及去重需使用者自行確認。 |
| 瀏覽器落盤 | 產品不能驗證，維持啟動下載文案；測試另讀四個實體檔，不保證其他瀏覽器下載一定成功。 |
| 手機／焦點／額外下載驗收 | 由本流程實測320/390及四檔，不宣稱實體裝置／輔助工具通過；裝置差異仍可能存在。 |
| 完整測試非reviewer重跑 | 作者跑完整suite並讀exit0，reviewer看diff及純探針；不把作者測試當獨立重跑證據。 |
| 正式部署／正式DB／帳號操作 | 不執行，維持本機提交；仍需獨立發布與正式驗收。 |
| PostgreSQL runtime | 沒有新DB/schema變更，專用庫未提供仍skip；不代替前階段PG發布驗收。 |
| 最後文件更新 | README/privacy/spec/本紀錄由本流程補齊；後續改動仍需維護文件避免落差。 |
| 原日期解析／修正store全面重審 | 本階段只審新整合，沿用前階段測試；可能仍有未發現的上游錯誤，匯出前人工核對不省略。 |
| 登出後其他tab既有private DOM | 沿用既有當頁記憶體行為，沒有新增跨帳號讀取／保存；共用裝置舊tab仍應關閉，未全面重寫session頁面生命週期。 |
| todo列被篩選／重繪後async下載 | 已明確點擊的匯出保留當時snapshot，沒有證據顯示錯誤payload；若期望篩選即取消下載，需另定取消語意。 |

第五階段只保留設計銜接：可靠URL／ID比對、保留來源／原文／更新紀錄、期限變更提示及私人原文不公開。本次沒有自動合併、標題近似推薦、Calendar授權或全面擴增來源。

交付前文件更新後相關頁面／隱私／帳號測試：25 passed、2 warnings、60.65秒，exit0。六項Node再驗證均exit0，採失敗即停止檢查；本階段diff --check通過。原目錄Dashboard／字型／readiness既有修改未動，保留本機隔離工作區，不push。已關閉本次QA分頁、重設viewport並停止合成預覽服務。
