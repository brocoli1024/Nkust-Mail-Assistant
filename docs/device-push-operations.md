# 裝置截止推播維運

本期沿用既有 Render／Neon，Cloudflare 只觸發固定工作。新程式預設不啟用推播，不新增 Gmail 或 Calendar 授權。正式狀態與驗收見 `device-push-validation-2026-11-10.md`。

## 設定與祕密

Render 需要下列七個設定：

| 設定 | 用途 |
|---|---|
| NKUST_PUSH_ENABLED | 先設 false；完成備份、遷移、部署與檢查後才 true |
| NKUST_PUSH_VAPID_PUBLIC_KEY | P-256 未壓縮公鑰的 base64url；可公開 |
| NKUST_PUSH_VAPID_PRIVATE_KEY | 對應 32-byte 私鑰 base64url；保持祕密 |
| NKUST_PUSH_VAPID_SUBJECT | 首次設定工具預設本站 HTTPS 網址，不公開管理者 Email |
| NKUST_PUSH_TRIGGER_SECRET | 獨立內部觸發憑證，Render／Cloudflare 使用同一組 |
| NKUST_PUSH_RATE_HASH_KEY | 獨立限流／端點指紋 HMAC 材料，不與觸發憑證混用 |
| TOKEN_ENCRYPTION_KEY | 沿用既有值；本次不要重設，Push 使用不同 context |

由擁有者在自己的互動終端執行 `python -m app.push.keygen`，輸入 GENERATE 才顯示首次設定值。非互動／輸出重導環境拒絕產生，避免進入 agent 或 CI 日誌。不要貼到聊天、Git 或公開工單。已有正式 VAPID 金鑰時不要重建；輪替須安排原訂閱重設。若透過瀏覽器設定，新憑證由本人輸入及提交。

Cloudflare 只設 Secret 型別的 NKUST_PUSH_TRIGGER_SECRET。不放資料庫、Gmail、OAuth、Session 或 VAPID 私鑰。

## 有序發布

1. 保留現有備份；先建立新鮮的同專案備份並核對還原能力。Neon 免費快照名額已由舊快照占用，不刪除舊快照或升級方案來騰空間。可在同專案建立含資料與 schema 的備份分支；正式 production 不切換預設分支。備份含私人資料，不能接公開應用或提供他人權限；完成後的清理由擁有者另行決定。
2. 推送已驗收程式到既有 codex/web-deployment，Render 仍採手動部署。GitHub main 工作流程 checkout 此分支；公開 CLI 明確相容 0010／0011，原來源排程在新增私有表前後都可使用。網站與 deployment_check 仍只接受 0011。
3. 在 production／public schema 核對 alembic_version=0010、目標專案與備份後，執行 `scripts/sql/device_push_0011_upgrade.sql`。此檔由凍結遷移離線產生，包在交易內，先驗 revision，再新增五張私有表與索引並更新版本；不改既有公告、Gmail 或 OAuth。新表不授權公開同步角色。不要執行 downgrade。
4. 先以 NKUST_PUSH_ENABLED=false 部署，檢查公開公告、公務公告、來源管理者與原 GitHub 收錄仍正常。回復版本必須包含 schema0011、IDBv3 及安全 SW 相容性；不能直接回到舊 v2 opener。
5. 本人完成祕密值，核對免費方案、用量及同源／代理條件；在必要的當下安全確認後才啟用 Render flag 與 Cloudflare cron。真機自行授權，觀察至少兩次真正 scheduled run；沒有 iPhone 實機結果不能宣稱 iPhone 已驗收。

## Cloudflare Worker

原始碼 `workers/deadline-push/src/index.js`；設定檔 `wrangler.jsonc`。服務名 nkust-deadline-push，只有 scheduled 工作；HTTP fetch 回 404，不建立公開資料查詢接口。

每五分鐘 `*/5 * * * *`，只向固定 `https://nkust-mail-assistant.onrender.com/internal/push/run` 發空 POST 與 Bearer 憑證；禁止轉址，150 秒有界逾時，不自動重送不明請求。只記安全結果碼。不要把 Worker 的手動測試當成真正 cron 已驗證。

Cloudflare cron 設定傳播可能需要最多約15分鐘；以實際 scheduled 日誌確認。[官方 cron 文件](https://developers.cloudflare.com/workers/configuration/cron-triggers/)

Render 免費工作區每月750小時共同計算；五分鐘檢查可能使單一服務接近整月運行。冷啟動、網路、免費額度、推播服務及裝置離線可能延誤；不保證五分鐘內顯示。不得自動升級方案。超額網路／建置另有規則，發布前核對帳戶設定。[Render 免費限制](https://render.com/docs/free)

啟動目前停用 proxy headers；不能將任意 X-Forwarded-For 當真實 IP。匿名建立／來源解析的 peer 桶可能共用入口 IP，先核對真實多人使用與限流回覆，不能用信任所有代理的方式繞過。保留每裝置與全站持久配額。

## 狀態與恢復

- 日期以台灣顯示、UTC 保存；精確截止預設24小時前，只有日期預設前一天09:00，不猜23:59。未知、未確認、過期或已過預設時間不能直接排程。
- pending／retry 是等待；accepted 只是服務接受，unknown 不盲目重送。用固定 tag 減少重複，不宣稱 delivered／read。來源變更先核對，不自動推定新期限。
- 完成／移除與取消 outbox 同一 IndexedDB 交易；離線時只稱待同步。較新取消可覆蓋已過時的 expected server revision，但不得越過較新的 client revision 或不同 epoch。
- 裝置寫入攜帶 expected_epoch；cookie 改變時拒絕舊意圖。遺失停用回覆時可明確重設：只停用／退休舊 epoch 的本機提醒佇列，待辦保留，伺服器取消狀態若未知照實標示。
- 404／410 清除端點；裝置停用立即清除伺服器日期。終止排程資料及回執七天清理，最少版本 tombstone 保留至裝置到期，避免舊請求復活。測試通知不占正式待辦識別配額，舊測試工作可移除。裝置最長400天、提醒最遠366天。

既有公開資料與私有 Gmail 保持隔離；不得把任何端點、auth、cookie、私鑰或郵件正文寫入日誌。瀏覽器 PushSubscription.toJSON 可能含 expirationTime；客戶端只挑 endpoint、p256dh、auth 送入嚴格 API。[W3C Push API](https://www.w3.org/TR/push-api/#dom-pushsubscription-tojson)

## 驗收與回復

`NKUST_TEST_POSTGRES_URL` 必須是獨立 loopback nkust_disposable* 測試庫；另設 NKUST_PUSH_TEST_DISPOSABLE=yes。不得使用 DATABASE_URL 或正式 Neon。若做受限角色驗收，NKUST_TEST_PUBLIC_SYNC_URL 必須指向同一測試庫且 username=nkust_public_sync。驗收器拒絕連線 query 覆寫並移除 libpq 環境覆寫，任何略過使整體失敗。

PowerShell：`./scripts/verify-push-postgresql.ps1 -PythonExecutable <本機虛擬環境python>`。`-PushOnly` 供較小的 PostgreSQL 核心回歸；正式驗收仍跑全套與19項 Node 檢查、原生瀏覽器 harness。

相容回復分支 `codex/device-push-rollback-20261108`，驗收 SHA `d4a8383bad690bc79493dec9c7f655f52c10a585`。先關閉 flag 與 cron，使用已授權維護流程持久停用未送工作，再部署相容回復程式。保留五張新表，不回寫舊備份覆蓋正常資料，也不刪瀏覽器資料庫；重新啟用須重新核對，避免舊工作復活。已提交服務的通知不能保證撤回。
