# Code CI 與發布門檻

## 流程

`.github/workflows/ci.yml` 在 Push 到 `codex/web-deployment` 或 `codex/ci-pipeline`、以 `codex/web-deployment` 為目標的 PR，以及手動執行時運作。

1. Python 3.12、Node 22 與一次性的 PostgreSQL 16 service container。
2. 安裝開發及 Web 依賴，執行 `alembic upgrade head` 與全部 pytest。
3. pytest-socket 限制測試中的 Python socket 只能連線本機；Google、Gmail、公告來源使用既有測試替身。此限制不涵蓋子程序；子程序測試也必須保持離線。
4. 檢查 JUnit 報告：所有測試不得失敗或跳過，且三個實際 PostgreSQL 測試模組必須出現。離線 SQL 編譯不算 PostgreSQL 實測。
5. Ruff 檢查程式正確性；pip-audit 掃描正式與開發依賴及其間接依賴。掃描出漏洞或掃描本身失敗都會阻擋 CI。

Ruff 第一階段只啟用 E9、F63、F7、F82，避免把既有程式格式重整混入 CI 修改。這不是完整型別檢查或完整安全稽核。

維運擴充另加入 Container recovery drill：編譯 Azure Bicep、建置 Docker、實際停止隔離 PostgreSQL 並驗證恢復與備份還原。`CI gate` 同時要求這項工作成功。詳見 [維運文件](operations.md)。

CI 不引用任何 repository secrets，不讀取正式 Neon 連線或 Gmail 憑證。資料庫帳密及 OAuth 設定均為合成值，資料庫隨 runner 銷毀。不要把 `.env`、token、真實郵件或資料庫備份提交到 Git。

## 必須在平台完成的設定

本機 YAML 修改不代表遠端保護已生效。

- GitHub：對 `codex/web-deployment` 設定 branch protection / ruleset，要求 PR 與 `CI gate` status check，禁止略過必要檢查（包含管理員）；不要開放直接推送繞過 PR。
- Render：本次 `render.yaml` 加入 `autoDeployTrigger: checksPass`。若服務由 Blueprint 管理，確認 Blueprint 已同步；否則在服務 Settings 將 Auto-Deploy 設成 **After CI Checks Pass**。確認部署追蹤分支為 `codex/web-deployment`。
- 手動部署與管理員略過是獨立通道；此 CI 不會自動禁止平台管理員的手動操作。

## 故意失敗驗收

請在 CI 設定發布後，留下 run URL、commit SHA 與結果作為證據。

1. 在測試用 PR 分支加入 `tests/test_ci_failure_drill.py`，內容為 `def test_ci_failure_drill(): assert False`，開啟以 `codex/web-deployment` 為目標的 PR。不要把故意失敗的測試合併。
2. 確認 pytest 與 `CI gate` 失敗，GitHub 的合併被必要檢查阻擋。
3. 確認 Render 已設定等待 CI，且正式服務部署版本沒有因這個 PR 改變。若要驗證 Render 對「被追蹤分支的失敗 commit」確實拒絕自動部署，使用獨立 Render 測試服務及測試分支演練；未合併 PR 本來就不會觸發正式分支部署，不能單憑這點宣稱部署門檻通過驗收。
4. 移除失敗測試，確認同一 PR 的全部工作與 `CI gate` 轉綠。

另可手動執行 Code CI，勾選 `failure_drill`，以合成失敗測試驗證 workflow 的失敗傳遞。這個快捷演練本身不能證明 PR 保護或 Render 設定已生效。

## 本機驗證

使用獨立測試 PostgreSQL，將 `NKUST_TEST_POSTGRES_URL` 與 `DATABASE_URL` 指向它，禁止使用正式資料庫。先安裝 `requirements-dev.txt`、`requirements-web.txt` 與 `requirements-ci.txt`。

```sh
python -m alembic upgrade head
python -m pytest -q --allow-hosts=127.0.0.1,localhost,::1 --allow-unix-socket --junitxml=ci-results.xml
python scripts/check_ci_report.py ci-results.xml
python -m ruff check app alembic scripts tests
python -m pip_audit -r requirements-web.txt
python -m pip_audit -r requirements-dev.txt -r requirements-ci.txt
```

缺少測試 PostgreSQL 時，可執行一般 pytest，但 PostgreSQL 測試會跳過，而且報告門檻會刻意拒絕該結果。

## 2026-11-18 本機驗證紀錄

- Windows / Python 3.14：完整測試 456 passed、37 skipped；加入 CI 相同的 socket 連線限制後結果相同。37 項皆屬於三個 PostgreSQL 實測模組，本機沒有提供獨立 PostgreSQL。
- 報告門檻測試：7 passed（包含錯誤 XML）；Ruff 與 YAML 解析通過。
- `requirements-web.txt` 與 `requirements-dev.txt` + `requirements-ci.txt` 的 pip-audit 均回報無已知漏洞；這是當次解析出的依賴結果，未來仍須每次掃描。
- 合成測試刻意 `assert False`：pytest exit 1，報告門檻 exit 1；故意失敗的暫存測試已移除。
- 含 37 項 skipped 的完整報告會被門檻拒絕，未把本機結果當成 PostgreSQL 驗收成功。
- 尚未驗證：GitHub Ubuntu / Python 3.12 實際執行、PostgreSQL service container、遠端必要檢查設定、Render 設定同步及端到端發布阻擋。

參考：[GitHub required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[Render auto deploy](https://render.com/docs/deploys)、[Blueprint](https://render.com/docs/blueprint-spec)。
