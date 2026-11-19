# 健康檢查、容器示範與復原

所有變更先放在 `codex/ci-pipeline`。推送本分支只執行 CI；不會合併 Render 正式分支。Azure workflow 只有手動觸發。

## 健康與監控

| 路徑 | 功能 | 存取 |
| --- | --- | --- |
| `/health/live` | Web 程序可回應 | 公開，只有狀態 |
| `/health/ready` | 資料庫可連線且 Alembic revision 相符；失敗回 503 | 公開，不提供錯誤細節 |
| `/health/status` | HTTP 次數、5xx 比率、平均耗時、同步各狀態次數、最後成功時間及資料年齡 | `Authorization: Bearer <MONITORING_TOKEN>` |

`MONITORING_TOKEN` 必須以 hosting 環境變數設定且至少 32 字元；未設定時 status 回 404。不要放在 URL。HTTP 統計為單程序啟動以來的累計值，重啟歸零；同步統計由資料庫持久保存，包含 recent/history/reclassify。多副本須由外部監控彙整。此版沒有宣稱提供滑動視窗或 p95。

`nkust.operations` 輸出 JSON 到 stderr，只包含路由樣板、狀態碼、耗時、同步工作 ID、計數與固定錯誤分類。不記錄 query、request body、郵件、IP、使用者 ID、Token 或原始 exception。未匹配的 URL 一律標為 unmatched。Render 健康路徑改為 `/health/ready`；需同步 Blueprint 才生效。公告過期不影響 readiness。

## 警示啟用

健康探測仍會留下請求日誌，但不計入 HTTP 請求數、平均延遲或錯誤率。就緒探測失敗時，`readiness_failed` 事件會區分 `database_unavailable` 與 `schema_mismatch`，回應仍只提供 503 和 `not_ready`。

1. 在服務環境與 GitHub Secret 設定相同的 `MONITORING_TOKEN`。
2. GitHub Variables 設 `MONITOR_BASE_URL=https://你的網站`（不加路徑）、`MONITOR_ENABLED=true`。
3. 手動執行 Service health monitor，確認正常／失敗狀態。排程每 15 分鐘執行，但 GitHub 排程只讀預設分支，因此僅推送功能分支不會啟動排程。
4. 在 GitHub 個人通知設定啟用 Actions 失敗通知。此版以 workflow failure 交付警示，沒有默默傳送 email/Slack；是否送達必須用實際帳號驗收。

告警條件：無法取得健康資訊、從未成功同步、超過 3 小時無成功同步，或至少 20 次請求且啟動以來 5xx 比率大於 5%。GitHub cron 不保證準時，正式服務可另接外部 uptime monitor。Azure 合成示範沒有真實同步，若使用相同 freshness 監控，會預期收到從未成功同步告警。

## 本機容器（只用合成資料）

```sh
docker compose up --build --wait
```

開啟 `http://localhost:8000/demo`。Web 以非 root 帳號執行，PostgreSQL 不暴露主機埠，不掛載正式資料或 .env。Demo 模式只允許固定隔離資料庫或容器內的 SQLite，覆寫 Google 憑證並拒絕帳號／Gmail 路由。Compose 固定使用合成監控 Token，僅綁定主機 127.0.0.1；不要把這份設定當正式部署。

Docker build 使用 allow-list context，映像僅包含 app、alembic 與 Web 相依套件，不包含 .git、.env、郵件資料庫或根目錄憑證。正式容器可設定 DEMO_MODE=0 並提供必要環境，但需另做正式部署驗收。

## 可重複的故障／備份演練

```sh
python scripts/recovery_drill.py
```

工具固定建立全新的 `nkust-recovery` Compose project，若同名容器已存在就拒絕操作，不接受任何正式資料庫 URL。流程：建立合成資料 → pg_dump → 暫停 db → 確認 live 200 / ready 503、輸出 JSON 告警 → 啟動 db → 確認 ready 200 → 還原備份到另一個 `nkust_restore` 資料庫 → 驗證合成 marker → 檢查 503 日誌 → 清除本次容器。

CI 的 Container recovery drill 工作會執行同一程序。成功時輸出 `recovery_drill_passed` 與量測秒數；這是演練觀測值，不是正式 RTO 承諾。若 port 8000 已有服務占用，先停止自己的 demo Compose；不要停止正式站。

## 回復版本與 Migration 相容性

演練使用正式監控程式的同一套探測邏輯，驗證正常時無告警、斷線時回報 `MONITOR_UNAVAILABLE`、恢復後告警清除。還原後比對 Alembic 版本和合成資料，`recovery_seconds` 只計到服務及監控恢復。實際通知送達仍需在設定通知的環境驗收。

- 部署失敗：先記下失敗 commit／image tag；以既有平台回復上一個已驗證版本。Azure 使用 revision，Render 可指定上一個 commit；本文件不會自動操作正式服務。
- 程式回復不等於資料庫回復。既有啟動程序會先升級 Migration，舊版程式也有嚴格 revision 檢查；新 revision 上線後舊映像可能拒絕啟動。因此只有確認同 revision 且相容時才能直接回復舊映像。
- Schema 變更採 expand/contract：先新增可選欄位、部署能讀新舊格式的程式、回填與驗證後，再於後續版本移除舊欄位。需要跨 revision 回復時，先在隔離副本驗證舊版啟動；不可把 `alembic downgrade` 當成無損保證。
- 資料還原：先建立獨立資料庫，用 pg_restore 還原並檢查 revision、資料筆數與合成／業務抽樣，再規劃切換連線。正式資料還原與切換須另外批准並安排維護時間。
- 本次沒有新增或修改資料庫 Migration。跨版本相容性與正式備份還原仍需對未來的實際 schema 變更驗證。

## Azure 示範 IaC 與 OIDC

CI 另以無外部網路的容器驗證 Azure 示範使用的 SQLite 啟動模式。Azure 手動部署完成後會檢查公開 HTTPS 入口、資料庫就緒、示範頁 200 與 Google 登入 403。GitHub 手動工作流程需在儲存庫預設分支可用，執行時再選擇 `codex/ci-pipeline`。

`infra/azure/foundation.bicep` 建立 ACR Basic、Log Analytics、Container Apps Environment、拉取映像專用 Managed Identity／AcrPull。`app.bicep` 部署單副本合成 Web，使用 SQLite 暫存資料及獨立監控 secret。重啟可能清空示範資料；不得用於真實郵件或正式資料。這裡不建立付費 PostgreSQL；PostgreSQL 驗證留在 CI／Compose。

先由擁有者建立專用 Azure resource group，確認區域、額度與預算。ACR 和日誌可能持續計費，即使 Web scale-to-zero 也不代表零成本。

GitHub 建立 `azure-demo` environment（建議指定 reviewer），設定 Variables：`AZURE_CLIENT_ID`、`AZURE_TENANT_ID`、`AZURE_SUBSCRIPTION_ID`、`AZURE_RESOURCE_GROUP`；Secret：`MONITORING_TOKEN`。Entra federated credential 的 subject 應為 `repo:brocoli1024/Nkust-Mail-Assistant:environment:azure-demo`，audience 為 `api://AzureADTokenExchange`。部署身份僅授權專用資源群組的資源部署與 role assignment 權限（例如 Contributor 加 Role Based Access Control Administrator，後者限此群組）。不用長期 Azure client secret。

先確認同一 commit 的 Code CI 通過，再手動執行 Deploy isolated Azure demo。workflow 也會檢查該 SHA 的 CI gate，接著部署基礎設施、ACR build，以 SHA 標記映像，再部署 Web。初次 role assignment 可能有傳播延遲，若拉取映像被拒，待角色生效後重試，勿開啟 ACR admin 密碼。

驗收後從 Azure Portal 檢查專用 resource group 的資源清單，刪除**該示範群組**以清理環境；同時移除不再使用的 OIDC 信任及 GitHub environment。不要使用正式服務所在群組。

參考：[Container Apps Bicep](https://learn.microsoft.com/azure/templates/microsoft.app/2025-01-01/containerapps)、[Azure OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)。

## 實際驗證紀錄（2026-11-18）

[GitHub Actions run 44222677926](https://github.com/brocoli1024/Nkust-Mail-Assistant/actions/runs/44222677926)：Ubuntu / Python 3.12 的 497 項測試全部通過、沒有跳過，包含獨立 PostgreSQL。Ruff 與兩份 Bicep 編譯成功。容器演練實際產生 DATABASE_UNAVAILABLE 告警，恢復後 ready 200，pg_dump 備份還原到第二個資料庫並驗證合成 marker；演練計時約 2.01 秒。

該次依賴掃描因 PyPI 15 秒網路逾時而失敗，CI gate 正確阻擋。已將掃描 timeout 提高為 60 秒；不忽略漏洞或掃描失敗。Azure 資源部署、外部通知送達與正式 Render 設定尚未執行。
