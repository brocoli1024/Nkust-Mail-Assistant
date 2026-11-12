# 裝置推播與主畫面引導驗收（2026-11-10；11-12補驗）

狀態：正式推播 API 已啟用；兩輪真實 Cloudflare cron、iPhone 測試通知實收與點擊回待辦已通過。11-12本人確認未按測試按鈕、到設定時間自動收到通知，且點擊回到對應公告；正式deadline另有accepted紀錄。核心上線流程驗收完成，其他實機條件仍列限制。不得把服務接受或測試通知成功寫成所有截止通知均已送達。

## 正式環境

| 項目 | 實際狀態 |
|---|---|
| Render | 既有 Free 服務，正式程式 ab3dedf，2026-11-10 15:09:22（Asia/Taipei）Live；NKUST_PUSH_ENABLED=true |
| Neon | 原專案 PostgreSQL18、production、公用 schema0011；未新增服務或升級方案 |
| Cloudflare | Workers Free，nkust-deadline-push，每5分鐘；程式對應432320b，憑證更新另有平台版本 |
| 真 cron | 14:50:46、14:55:42兩個 scheduled 事件均有 PUSH_TRIGGER_OK；不是預覽或手動測試 |
| iPhone | 本人確認從主畫面 App 操作，實際收到測試通知，點擊可回我的待辦；資料庫另有 test accepted 紀錄 |

主畫面入口、公開公告、公務公告（原收錄清單）、待辦與詳情返回已在正式站操作確認。加入主畫面不自動授權通知；每筆提醒須本人核對截止與同意。測試通知回 /todos，真正截止／來源變更提醒才回公告詳情。

Render 發布前實際查到 Auto-Deploy 為 On Commit，已先保存 Off，才推送與手動發布。只更新既有 codex/web-deployment；main及原工作流程不改。原公告收錄第41輪的既有失敗已重跑成功，feed／articles／office_mail／discovery均退出0；discovery仍有有界待處理警告，不宣稱全部歷史公告已收完。沒有變更Gmail來源帳號、OAuth、Session或既有加密金鑰。

## 測試證據

- 本期原完整獨立 PostgreSQL：817 passed、0 skipped（139.96秒）；目標本機127.0.0.1:55439、全新合成schema、非管理員owner及受限nkust_public_sync。正式Neon未用於開發測試。實際簽章修正後於11-12完成完整獨立回歸：820 passed、0 skipped，321.15秒，驗收器退出0；本機測試PostgreSQL已停止。
- 最新傳送、設定、裝置、邊界、API及dispatcher回歸：52 passed。涵蓋實際設定工具的HTTPS Subject，使用真實pywebpush加密／VAPID簽章及假的網路邊界，沒有用部署秘密做測試。
- 重新列出並逐檔執行18個 tests/*check.cjs，全過。先前文件19項為計數誤植；原生瀏覽器harness另列，不混算。
- Chrome 原生IDB：v2→v3保留、quota／abort一起撤回、未opt-in零上傳、離線取消、晚到建立後取消確實同步、busy第二筆不漏送、舊epoch不清新裝置、重設仍保留待辦均觀察PASS。本機合成表單最少資料同步與前一天09:00規則PASS；手機390×844引導檢查及對比修正已做。
- 一次獨立全變更審查提出1項Critical、10項Important及1項Minor，已在45f9c7d逐項重現修正。未將原審查假稱為修正後再次獨立批准。兩個既有Starlette／anyio棄用警告仍存在。

## 備份、遷移與回復

同專案完整備份 push-pre0011-20261110（br-summer-river-az0m4c40），由production br-frosty-term-azcuok6j建立；保留原舊手動快照與預設分支，未升級方案或開放新讀取者。

從備份建立 push-restorecheck-20261110（br-muddy-thunder-azc0z6w9）。先確認schema0010與原資料彙總一致，再套凍結0011交易；原有使用者／郵件／私人公告／公開公告彙總未變，公開同步角色無push_devices SELECT。production之後套相同交易，遷移當下再次確認彙總一致與權限拒絕。沒有在文件記錄私人資料筆數、連線字串或憑證。

相容回復分支已推送：codex/device-push-rollback-20261108，d4a8383bad690bc79493dec9c7f655f52c10a585。獨立PG smoke及原生IDBv3回復讀取／取消PASS。回復須先停flag／cron、持久停用未送工作，保留新表與IDBv3；不能直接部署舊v2 opener、downgrade或用舊備份覆蓋正常資料。詳見[維運文件](device-push-operations.md)。

## 正式驗收發現並修正

1. Cloudflare Workers不實作redirect:error，請求尚未送出就TypeError。改manual並拒收3xx；補302／401／503及無敏感內容診斷測試。本人同步同一Trigger Secret並Deploy後，兩輪真cron成功。[官方Request文件](https://developers.cloudflare.com/workers/runtime-apis/request/)
2. 初始設定Subject結尾斜線被py_vapid嚴格sub驗證拒絕。先前只驗字首與金鑰配對、以及mailto合成案例，漏掉真實預設。已以真實設定重現RED→GREEN，移除非秘密Subject結尾斜線，啟動前用公開sign介面驗實際簽章；不關閉嚴格驗證、不更換金鑰或重建訂閱。
3. 初期結果不明的測試沒有盲目重送。傳送診斷只記固定分類，Worker只記有界HTTP狀態碼，不記例外字串、正文、端點、auth或秘密。新憑證與修正均由本人輸入提交；未進聊天、Git或CI。

## 尚待完成與限制

- 真正截止提醒：11-12本人已明確確認到時自動出現且點擊回到對應公告，與deadline accepted紀錄一致，核心端到端通過；鎖定畫面條件未另外確認。
- 真機撤銷／拒絕授權、取消後不再收到、桌面／Android：尚未實機驗收；相關隔離、取消競爭與狀態行為已有獨立PG／瀏覽器驗證。
- 稍後處理不變動另行設定的提醒；清除裝置資料可能失去管理能力，須照UI重設並重新核對。Safari分頁與主畫面App資料可能分開，不自動上傳搬移。
- 免費服務、冷啟動、網路、推播提供者與裝置設定可能延遲；accepted不等於已顯示／已讀。未知結果不盲目重試；測試每裝置每小時最多3次，舊unknown不當成未送成功而任意重送。

Task8的本機、獨立PG、正式部署、真cron與iPhone核心端到端交付已完成。其他裝置與撤銷／取消實機條件仍未驗，不宣稱所有裝置、所有情境均已測完。

## 2026-11-12補驗

- Render仍Live ab3dedf。Cloudflare近一小時顯示0 Errors，23:00、23:05、23:10等scheduled事件皆PUSH_TRIGGER_OK；沒有重新部署、重建角色或更換秘密。
- 正式Neon只執行截止／測試狀態分組SELECT，確認真正deadline已有accepted，沒有讀取裝置端點、郵件或秘密，沒有修改提醒。
- 上次完整回歸的未完成紀錄不算通過。新一輪將合成本機PG啟動、完整驗收及finally停止放同一受控行程，820項全過、0略過、2個既有相依棄用警告；完整結束後已停止測試庫。

- 最後本人回覆：「自動出現，點擊回到對應公告」。此為真實自動公告提醒，不與手動測試通知混算。測試時暫改的提醒時間由本人調回所需值，系統不擅自修改私人提醒。
