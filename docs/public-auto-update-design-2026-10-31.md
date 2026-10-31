# 正式入口與每小時公開更新

使用者要求直接進公告、正式介面移除合成示範、無人開站仍每小時更新，保留既有待辦功能。

入口採/導向/public/announcements，保留查詢字串。一般導覽、登入、空白與錯誤頁不再導向demo；正式預設停用demo；舊demo網址轉到公告清單，僅內部測試明確demo_enabled=True才掛載示範。公告列表保留既有篩選／來源狀態與待辦入口。

沿用GitHub Actions，每小時17分執行；schedule必須放預設main，工作checkout codex/web-deployment的網站程式。僅contents:read、不接PR事件，單一concurrency且不取消執行中同步、timeout10分鐘、可手動workflow_dispatch。GitHub排程可能延後，不保證整點；公開repo60天無活動可能被平台停用，失敗以Actions顯示，不偽稱零維護。

新建專用資料庫role nkust_public_sync，只允許連線neondb、public schema usage、讀alembic_version、對public_announcements/public_source_states/public_sync_runs/public_source_versions的SELECT/INSERT/UPDATE與對應id序列USAGE/SELECT。不授權emails/users/analysis/私人修正/待辦/私人版本、schema CREATE或角色管理；不授權DELETE或歷史補收表。沿用既有sync_recent、SourceLease與失敗rollback，不增API。

唯一新secret NKUST_PUBLIC_SYNC_DATABASE_URL交給本repo的Actions；不複製Gmail、OAuth、Session或管理員金鑰。由Neon產生新role密碼，不改現有角色；將role連線存repo secret需執行時明確確認。正式連線不放Git、聊天、命令參數或輸出。

測試：首頁導向與query保留、一般頁無demo入口；同步成功/部分/失敗保留資料；專用role可更新公開表及版本但讀私人表、改schema、刪資料必須拒絕。獨立PG驗證後才設定正式權限與secret；先手動執行Actions成功，再驗證正式最後更新時間。不得聲稱未實際發生的下一小時排程已成功。

Neon介面建立的角色會繼承管理權，SQL擁有者無法縮限；已經使用者當下授權刪除未使用角色，改SQL CREATE ROLE建立，正式查驗createdb/createrole/bypassrls/elevated/private_read皆false。密碼由使用者在SQL Editor親自觸發隨機生成設定，代理不代為執行憑證設定。


## 最新驗收與執行紀錄

2026-10-31：首頁直達公告、正式預設停用示範、超過2小時未成功更新提示已通過獨立 PostgreSQL 18.6 全套驗收：575 passed、0 skipped（2個既有套件棄用警告）；6項 Node 前端檢查全通過。測試庫已停止，不使用正式資料庫。

受限角色已於正式 Neon 透過 SQL 建立並查驗權限；使用者親自執行已保存的 Public sync credential setup 查詢設定密碼。NKUST_PUBLIC_SYNC_DATABASE_URL 已加密存入 GitHub Actions Repository Secret，未將憑證存入版本庫或驗收輸出。正式排程發布及首次執行結果另記於發布紀錄。

介面以最後成功更新時間為準。超過2小時（嚴格大於，含無成功紀錄）顯示提醒；來源更新失敗或部分失敗仍保留原有資料並提示，不因排程未執行而清空。
