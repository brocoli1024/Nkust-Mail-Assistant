# 維運能力實作計畫

**目標：**完成使用者提出的四項改善，提交到 codex/ci-pipeline，不合併正式站。
**設計：**保留現有 Web 與同步流程；新增健康路由、安全 JSON 日誌及受保護的彙總監控。Docker Compose 提供合成 PostgreSQL；Azure Bicep 提供單副本、可刪除的 SQLite 示範站，停用 OAuth。正式資料與憑證不進入示範環境。
**技術：**FastAPI、SQLAlchemy、Docker Compose、Bicep、GitHub Actions OIDC。
**規格：**本對話原始四項需求；採用使用者已指定的分支及中文提交。

## 全域限制
- 不讀取或故障注入正式 Neon/Gmail，不提交 .env 或既有無關修改。
- 健康就緒只依賴必要資料庫；公告過期獨立警示。
- CI 在新分支 Push 執行，所有新增測試需通過。
- Azure 資源建立與外部通知收件設定須由使用者提供帳號及目的地；本次提交部署檔及驗證工具。

## 工作
1. app/api/health.py 與 app/observability.py：live/ready、受 Bearer token 保護的 status、請求及同步 JSON 日誌；測試斷線/恢復、遮蔽、計數與授權。
2. Dockerfile、compose.yaml、app/container_start.py 與 infra/azure：合成模式、獨立 PostgreSQL、非 root 容器、Azure OIDC 手動部署；驗證設定及容器故障演練。
3. scripts/check_health.py、scripts/recovery_drill.py 與維運文件：健康/過期/錯誤警示、獨立資料庫停止與還原測試；CI 執行容器演練與 Bicep 編譯。
4. 完整測試與只讀審查，中文 commit，僅推送 codex/ci-pipeline。

## 審查重點
資料庫斷線不得阻塞過久或洩漏連線字串；未知 URL 不進入日誌；無監控 Token 不公開指標；示範不啟用 Gmail；容器映像不可包含工作區私密資料；還原只操作固定隔離容器。
