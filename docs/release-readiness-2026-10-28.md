# 公開公告版上線準備（2026-10-28）

## 範圍與正式環境

本次發布免登入公開校園公告、學生相關篩選、選取後立即篩選，以及既有私人郵件功能。公開資料與私人帳號分表保存。Google Gmail 的測試／驗證限制不因本次發布而解除。

2026-10-28 實際核對：Render 免費服務 nkust-mail-assistant，部署分支 codex/web-deployment，On Commit 自動部署；目前正式版本 e844624。建置 pip install -r requirements-web.txt，啟動 sh scripts/start-web.sh，健康檢查 /login。啟動腳本會先執行 alembic upgrade head，因此推送會觸發正式資料庫遷移至 0006。

Neon 專案 Nkust Mail Assistant、production 分支、PostgreSQL 18、新加坡、免費方案，歷史還原範圍為 6 小時。上線前已建立手動快照 production at 2026-10-28 02:03:10 UTC (manual)，台灣時間 10:03:10，無自動到期；未設定排程、未升級付費。此快照包含建立當時正式資料，不能宣稱刪除帳號會立即清除此副本。隱私說明已配合更新。尚未實際還原此 Neon 快照。

## 驗收證據

完整驗收：454 passed，0 skipped，2 個既有測試框架棄用警告，耗時 121.58 秒。測試使用獨立本機 PostgreSQL 18.6、非管理員測試角色及一次性測試庫，沒有使用正式 DATABASE_URL。包含 SQLite 與 PostgreSQL 資料合約、0005 至 0006 保留私人資料的遷移、租約併發與歷史游標測試。

實機測試發現資料庫以不同時區回傳相同時間時，內容指紋可能誤判更新。先新增回歸案例重現，再統一以 UTC 計算指紋；修正測試中對已帶時區時間不當替換時區的斷言。

pip-audit 檢查 requirements-web.txt 未發現已知漏洞；這是在 Windows／Python 3.14 解析的套件結果，不能代替 Render Linux／Python 3.12 部署後驗證。未檢視或記錄正式密碼、token、郵件內容。

## 發布順序

1. 確認 TOKEN_ENCRYPTION_KEY 與 SESSION_SECRET 已安全備份。不要將值貼在聊天或提交到 Git。
2. 確認發布版本後，推送 codex/web-deployment；Render 自動遷移並啟動。觀察遷移、部署結果及 /login 健康狀態。
3. 透過維護者本機的短期環境設定安全連到正式 Neon，執行 python -m app.public_cli sync --source nkust-latest。連線字串不可寫入 Git、聊天或紀錄。現有本機設定是 SQLite，不能直接用於正式匯入。Render 免費服務沒有可用的維護 shell；需在正式操作前建立這條維護連線。
4. 匿名檢查 /、/public/announcements、公告詳情與即時篩選；確認 /announcements 仍要求登入，再以既有帳號檢查私人資料隔離。公開頁應顯示真實收錄數、更新時間與歷史未完成狀態。
5. 分批執行 backfill --max-pages 5，持續查看游標與完整度；全歷史未完成前不得宣稱全部收錄。後續更新目前由維護者手動執行，沒有自動排程。

本文件不代表已推送、正式資料庫已遷移、公開資料已匯入或正式端驗收通過。

## 回復方式

部署失敗時先停止後續匯入並保留日誌，不直接刪表或還原整個正式庫。0006 只新增公開資料表，應優先回復已知可用的 e844624 應用版本並保留新增表；整庫快照還原會覆蓋快照之後私人資料的變更，須另行確認。保留原有加密與 session 金鑰，避免還原後無法解密授權。

既有未提交的 dashboard CSS／JS、index 模板、2026-10-01 readiness 文件及字型檔不納入本次發布提交，且已以原有雜湊確認未被改動。
