# 校園通知待辦助手最終檢查

> 2026-10-31補修狀態：下列四項缺口均已修正；獨立PostgreSQL 18.6完整測試571 passed、0 skipped。以下保留2026-10-30檢查當時狀態，最新證據見[補修與PostgreSQL驗收](campus-action-fixes-postgresql-validation-2026-10-31.md)。正式部署與其他裝置驗收限制仍適用。

檢查日期：2026-10-30（Asia/Taipei）。程式基準：9a7a5a6e6fcc4a8e4b8055661f3685f9accb3833。

## 結論

五階段核心功能已完成本機實作，原目標「免登入找公告 → 看懂行動與期限 → 自行加入待辦 → 追蹤完成」已有程式與自動測試支持。不能判定為零缺口或正式上線完成：仍有四項低影響問題，以及真實PostgreSQL／特定瀏覽器條件等未驗收項目。本次是檢查，沒有修正產品程式、部署、push、正式資料庫或OAuth變更。

## 需求與實際狀態

| 階段 | 實際程式／介面 | 結論 |
| --- | --- | --- |
| 1 降低門檻 | public_announcements與demo匿名路由；搜尋分類、合成標示、公開來源／更新狀態；public_sync失敗保留資料 | 核心已實作；公開錯誤重試會丟失原查詢條件 |
| 2 行動資訊卡 | action_cards/action_card_rules、原文引文與候選日期、分開deadline/event_date、私人修正歷史與公開IndexedDB | 核心已實作；兩項資訊顯示小缺口，見下節 |
| 3 我的待辦 | 明確加入、完成／重開／稍後／移除，裝置與帳號隔離，首頁優先；明日09:00台灣時間及到期重現 | 核心已實作；保存加入時快照，不會自動同步後來來源變更 |
| 4 行事曆 | 共用calendar-ics/controller，活動／截止選擇、日期確認、全天／台灣時間、來源與私人提示 | 已實作；只宣稱啟動下載，未測外部行事曆匯入結果 |
| 5 來源整理 | 官方文章網址保守精確關聯，public/private獨立版本表、原文與解析留存、日期差異及本人歷史 | 核心已實作；:443網址有漏列邊界，不實體合併或刪原文 |

日期與資格採保守處理：未知／衝突待確認，AI非唯一依據，適用對象不等於本人符合資格。公開資料不因私人來源關聯而包含私人郵件。新版本不會覆寫個人修正、待辦或已下載ICS。

## 仍存在的四項小缺口（本次核對程式）

1. app/services/source_views.py:98：候選篩選使用原始URL前綴，漏列正規化後相同的明列`:443`私人網址；official_identity雖可接受，候選已被排除。原文與歷史仍在。
2. app/web.py:138：公開錯誤重試固定返回公開清單，沒有保留搜尋／分類／頁碼或原詳情位置，可能要重新找公告。
3. app/static/web/action-card.js:65：JavaScript重繪依據只放引文，未重建來源標題／摘要種類標籤；原引用及完整快照仍保存。伺服器初始action_card.html有標籤。
4. app/templates/web/announcement_detail.html：私人詳情沒有呈現收到時間與原始分類，即使後端已有這些欄位；來源留存的原始資訊仍可查看。

這些是現存小缺口，不是此次新發現的資料外洩／遺失。過往單一階段的「無其他延期」只描述該階段，不能當成整個專案沒有既有小項。

## 新執行的驗證

完整pytest：518 passed、49 skipped、2 warnings，60.14秒，exit0；獨立basetemp=data/audit-cache/final-project-audit-1030，未使用正式資料庫。
六項Node檢查均exit0：calendar_integration_check、calendar_ics_check、todo_store_check、action_card_store_check、announcement_filter_check、pwa_worker_check。git diff --check通過。
49項略過為未配置專用PostgreSQL的測試；SQLite、離線SQL或過往舊版PG紀錄不能證明本次0007–0009及併發行為在真實PG已通過。2項是既有Starlette/httpx與anyio棄用警告，非測試失敗。
本次重跑自動測試及核對程式／文件，沒有重做瀏覽器操作；320/390手機、鍵盤焦點、A登出B隔離、分頁、實際合成ICS下載等使用前五階段已記錄的驗收證據，不宣稱是本次新增實測。

## 分支及上線界線

- 本機隔離worktree的HEAD為9a7a5a6，工作樹在檢查開始時乾淨；本報告是本次新增文件。
- main=8b60967（單人本機版）；本機codex/web-deployment=9a7d18c；目前HEAD比該分支多24個提交。這些新增實作尚未整合回該本機分支。
- 本機快取origin/codex/web-deployment=4271ad4。本次沒有fetch或查詢線上正式部署，不能以本機追蹤ref斷言遠端今天的狀態。
- 新版程式要求schema0009，正式環境不可直接假定相容；本對話未執行正式migration或部署。原README的舊日期「已部署／PG通過」不代表本次五階段已發布。

## 完成上線前還需要什麼

優先補四項小缺口；在獨立PostgreSQL測試庫驗證新版遷移、同步／修正／刪帳號併發；補停用JS、實體手機及輔助科技的目標驗收。第二階段計畫仍有三項明標部分完成，主要是這些執行環境與併發驗收條件，不能把勾選數量當成產品完成度。
之後才安排分支整合與獨立部署程序，確認備份／回復及資料保存策略。大量同URL來源比對與版本累積的容量尚未實測，需依預期使用量驗收。此次不自動部署或要求開啟新服務。
