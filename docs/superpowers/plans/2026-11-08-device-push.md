# 截止前裝置推播與加入主畫面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 免登入的公開公告待辦可經本人確認日期後設定裝置提醒，包含 iPhone 主畫面 App，並提供加入主畫面引導。

**Architecture:** 沿用 FastAPI、Neon 與 IndexedDB；Cloudflare 免費 Worker 每五分鐘只觸發固定 Render 工作。提醒必須 opt-in，本機待辦與提醒 outbox 原子保存；後端使用獨立匿名裝置身分、持久版本及工作租約。先完成推播，再完成安裝引導，最後處理正式啟用。

**Tech Stack:** Python／FastAPI／SQLAlchemy／Alembic／PostgreSQL、原生 JavaScript／IndexedDB／Service Worker、pywebpush 2.5.0、Cloudflare Workers。

**Spec:** [2026-11-08-device-push-design.md](../specs/2026-11-08-device-push-design.md)，使用者於 2026-11-08 同意。執行方式沿用本對話內實作。

## Global Constraints

- 「所有畫面採Asia/Taipei；伺服器保存UTC。」截止與活動日期分離，日期必須由使用者確認；原始依據仍存本機。
- 「加入待辦仍只保存在此瀏覽器，預設不開啟通知、不上傳完整待辦快照。」不新增 Google、Email 或私人 Gmail 提醒功能。
- 「支援iOS16.4以上的主畫面網頁App」；直接使用明確點擊手勢訂閱，不能先等待後端網路。
- 「成功只表示推播服務接受，不代表裝置已顯示或使用者已讀。」不保證五分鐘內送達。
- 「未完成這些前，不更動正式DB、啟用付費服務或宣稱截止推播已上線。」保留原 GitHub 公告收錄、OAuth、摘要及配色。

## Review Focus

1. 完成待辦時斷線或 IndexedDB 交易中止：本機狀態與取消 outbox 不得各自成功。任務 5 測試。
2. 舊建立請求晚於取消請求到達：即使尚未建立提醒，取消版本仍阻止復活。任務 2／4 測試。
3. Cookie 遺失但舊 PushSubscription／outbox 還在：不得跨裝置認領端點或上傳舊意圖。任務 1／5／6 測試。
4. 傳送逾時或程序在送出後死亡：狀態 unknown，不盲目重送、不顯示已送達。任務 3 測試。
5. 新版 IndexedDB 後回復舊程式：既有待辦仍可讀，不能以刪庫解決 VersionError。任務 5／8 測試。

---

## 檔案與共用契約

新增功能檔集中使用 push 命名；既有模組只作必要接線，不全面重構。以下路徑均相對本隔離工作區。

- 設定／保存：`app/push/config.py`、`app/push/models.py`、`app/push/repository.py`、`app/push/security.py`、`app/push/contracts.py`；套件加入 `app/push/__init__.py`。
- 日期／來源／發送：`app/push/dates.py`、`app/push/sources.py`、`app/push/transport.py`、`app/push/dispatcher.py`。
- 網頁／API：`app/api/push.py`、`app/static/web/push-store.js`、`push-client.js`、`push-ui.js`、`install-guide.js`、`app/templates/web/push_controls.html`、`install_guide.html`。
- 部署：`alembic/versions/0011_device_push.py`、`workers/deadline-push/src/index.js`、`workers/deadline-push/wrangler.jsonc`；既有 schema gate、Alembic metadata、web app 工廠及網頁腳本接線同步修改。

`contracts.py` 定義不可變型別：`PublicRef(id:int, source_ref:str, title:str, detail_path:str, version:str)`；`Deadline(kind: Literal['date','datetime'], value:str, confirmed:bool, basis: Literal['official','user'])`；`ReminderIntent(todo_id:UUID, source_ref:str, source_version:str, client_revision:int, operation_id:UUID, enabled:bool, deadline:Deadline|None, remind_at:datetime|None)`；`MutationResult(server_revision:int, client_revision:int, status:str)`。外部 JSON 拒絕未知欄位；不得接受 card、標題、全文或任意 URL。

日期函式 `validate_window(deadline:Deadline, remind_at:datetime|None, now:datetime)->ReminderWindow` 回傳 UTC `remind_at`、`expires_at`。`resolve_public_ref(session, source_ref:str)->PublicRef` 僅精確查現有公開資料。`PushRepository.apply_intent(device_id:UUID, intent:ReminderIntent, expected_revision:int|None, now:datetime)->MutationResult` 是唯一提醒寫入入口。

實作預設值：提醒最遠 366 天；裝置憑證有效 400 天，尚有未到期工作不得提前依閒置清除。每裝置最多 20 筆啟用提醒、全站最多 10,000 筆及 2,000 個有效裝置；超限保留本機待辦並提示。測試通知每裝置每小時 3 次、全站每小時 300 次；建立裝置每來源 IP 每小時 120 次、全站每小時 500 次；裝置變更每小時 120 次。配額以資料庫持久桶與交易檢查，值可由部署設定降低，不能自動放寬。雜湊 IP 桶 48 小時清理；不記錄原始 IP。未確認可信代理時只用實際 socket peer，正式門檻另驗校園共享出口不被誤鎖。

## Task 1: 預設關閉的設定、私有 schema 與匿名裝置

**Files:** 新增設定／保存五檔及 `tests/test_push_devices.py`、`tests/test_push_postgresql.py`；修改 `app/database/schema.py`、`alembic/env.py`，新增 0011 遷移。

**Interfaces:** `PushSettings.from_env()->PushSettings`；`PushCipher.encrypt(device_id:UUID, subscription_version:int, value:dict)->str`／`decrypt(...)->dict`；`PushRepository.register_device(token:str, subscription:dict, now:datetime)->DeviceState`。`DeviceState` 只含裝置 UUID、epoch UUID、訂閱版本、有效期，不回端點或金鑰。TOKEN_ENCRYPTION_KEY 沿用既有 Fernet 材料但使用 push 專屬 context，不改 Google token 流程。

- [x] **Step 1 — RED 測試：** `test_disabled_needs_no_push_keys` 斷言預設關閉；`test_device_isolation_and_redaction` 斷言 A 不能讀 B、DB 無明文 token／端點、repr 無秘密；`test_endpoint_cannot_be_claimed_by_new_device` 斷言 cookie 遺失不可認領舊端點；`test_0011_preserves_0010_and_public_role_denied` 驗資料保留與公開同步角色無新表權限。
- [x] **Step 2 — 跑 RED：** `python -m pytest tests/test_push_devices.py tests/test_push_postgresql.py -q`，確認因缺少新契約／遷移失敗，而非環境連線錯誤。PostgreSQL 只用獨立測試庫。
- [x] **Step 3 — 實作保存：** 建立 `push_devices`、`push_reminders`、`push_operations`、`push_leases`、`push_rate_buckets`，外鍵與唯一約束涵蓋裝置、todo_id、operation_id、endpoint 雜湊。裝置隨機 token 至少 32 bytes，DB 存 SHA-256；加密內含完整訂閱，endpoint fingerprint 用獨立 HMAC 材料。新增 NKUST_PUSH_ENABLED、VAPID_PUBLIC_KEY／PRIVATE_KEY／SUBJECT、TRIGGER_SECRET、RATE_HASH_KEY 設定，秘密欄位不輸出。關閉時不要求新金鑰。
- [x] **Step 4 — 跑 GREEN：** 重跑上述測試及 `tests/test_config.py`，全過；PostgreSQL 案例不可略過冒充完成。確認 schema gate 0011 與模型 metadata 都接好。
- [x] **Step 5 — Commit：** 僅加入本任務檔案，訊息 `feat: add isolated push device persistence`。不推送到正式分支、不遷移正式庫。

## Task 2: 可核對的截止、公開來源與有序提醒意圖

**Files:** 新增 `app/push/dates.py`、`sources.py`、`tests/test_push_dates.py`、`test_push_intents.py`；擴充 repository 與 PostgreSQL 測試。

**Interfaces:** 產出共用契約的 `validate_window`、`resolve_public_ref`、`apply_intent`。來源版本為公開語義內容的 hash，取 title、正文及已收錄官方相關頁內容；排除抓取時間、錯誤碼等暫態 metadata。詳情路徑由來源類型產生，不接受客戶端路徑。

- [x] **Step 1 — RED 測試：** `test_date_only_previous_day_taipei_0900` 斷言 11/10 截止預設 11/9 09:00+08、到期界線 11/10 00:00+08；`test_exact_minus_24h` 驗精確時刻；`test_unknown_or_elapsed_default_requires_confirmation` 驗未知日期／推定年份／過期及已過預設時間不自動建立；`test_cancel_before_create_is_tombstone` 驗 revision 2 取消後 revision 1 建立遭拒；`test_same_operation_is_idempotent` 驗重送相同意圖不增工作。
- [x] **Step 2 — 跑 RED：** `python -m pytest tests/test_push_dates.py tests/test_push_intents.py -q`，失敗指向缺少日期／來源／版本實作。
- [x] **Step 3 — 實作純函式及交易：** 時間一律帶時區；date 保留「官方未提供時間」語義，使用者另填日期標示 basis=user。拒絕未確認、非未來提醒、超過 366 天及不早於到期界線。source_ref 僅接受兩元素 JSON、兩個既有公開 source key 與精確官方 canonical URL；不存在不抓網路。以 client_revision 和 expected server_revision 防舊寫入，取消即使無既有提醒也保存 tombstone；先落 idempotency 結果再回傳。限額檢查與更新同交易。
- [x] **Step 4 — 跑 GREEN：** 重跑日期／意圖及獨立 PostgreSQL 併發測試：同時取消與建立、跨裝置相同 todo_id、來源僅抓取錯誤時版本不變、內容改變時需重核；全部通過。
- [x] **Step 5 — Commit：** `feat: validate confirmed deadline reminder intents`，只加入本任務檔案。

## Task 3: 安全 Web Push 傳輸與持久發送工作

**Files:** 新增 `transport.py`、`dispatcher.py`、`tests/test_push_transport.py`、`test_push_dispatcher.py`；修改 `requirements-web.txt`、`requirements-lock.txt`，沿用現有 pinned HTTPS 連線工具。

**Interfaces:** `PinnedPushSession.post(url, data=None, headers=None, timeout=None, **kwargs)->requests.Response`；`PushSender.send(subscription:dict, payload:dict, ttl:int, now:datetime)->SendOutcome`；`run_due(db, sender:PushSender, now:datetime, max_jobs:int=100, budget_seconds:int=50)->RunSummary`。Outcome 僅 safe code／accepted／retryable／unknown／invalid；RunSummary 只安全計數。

- [x] **Step 1 — RED 測試：** `test_endpoint_public_dns_and_no_redirect` 驗內網 DNS、重綁、userinfo、非 443 及 30x 全拒；`test_timeout_is_unknown_not_retry` 驗模糊逾時不自動重送；`test_expired_sending_lease_is_unknown` 驗 crash 後相同語義；`test_cancel_fence_before_send`、`test_changed_source_sends_review_only`、`test_410_erases_endpoint` 驗取消、變更提示與清理。
- [x] **Step 2 — 跑 RED：** `python -m pytest tests/test_push_transport.py tests/test_push_dispatcher.py -q`。傳送全用替身，不觸碰實際裝置。
- [x] **Step 3 — 實作傳輸與工作：** 使用 pywebpush==2.5.0 的公開 `webpush(..., requests_session=..., timeout=..., ttl=..., content_encoding='aes128gcm')`；每次複製 VAPID claims。相依版本由實際 resolver 與現有 lock 合併驗證，禁止自寫加密或使用私有 prepare 方法。初始精確 host 只允許 web.push.apple.com、fcm.googleapis.com、updates.push.services.mozilla.com；TLS/SNI、DNS 公網檢查及連線 pin，無轉址、無 requests 隱藏重試。單次網路最多 5 秒並受剩餘總預算限制；claim／重核短交易、網路交易外。429／明確 5xx 最多重試 3 次，退避 1／5／15 分鐘且不得超過 expiry；不明結果 unknown。不可將 WebPushException 原文寫入日誌。404／410 停用訂閱並清除加密端點；過期及終止工作只保留 7 天，清理每輪最多 100 筆。
- [x] **Step 4 — 跑 GREEN：** 重跑上述與 PostgreSQL 多 worker、訂閱換版、取消中競爭、run budget／backlog 測試；驗 accepted 不等於 delivered、TTL 不超過 expiry。紀錄送出前最後檢查後仍可能遇取消，已提交訊息不能撤回，不聲稱 exactly-once。
- [x] **Step 5 — Commit：** `feat: dispatch bounded deadline web push jobs`。

## Task 4: 同源匿名 API 與固定 Cloudflare 觸發

**Files:** 新增 `app/api/push.py`、`tests/test_push_api.py`、Worker 兩檔與 `tests/push_worker_check.cjs`；修改 `app/web.py` 工廠及 lifespan 接線。

**Interfaces:** GET `/api/push/config` 回 enabled、publicKey；POST `/api/push/device` 登記 subscription 並回 DeviceState；DELETE 同路徑關閉全部；GET `/api/push/reminders` 僅此裝置；PUT `/api/push/reminders/{todo_id}` 接 ReminderIntent 與 expected_revision；POST `/api/push/test` 只接受 operation_id；POST `/internal/push/run` 空 body、Bearer 獨立 Secret。公開來源解析 POST `/api/push/source` 只接 source_ref 並回 PublicRef。

- [x] **Step 1 — RED 測試：** `test_cross_origin_and_google_identity_cannot_authorize` 驗跨 Origin、無 Origin、非 JSON、Google cookie 代替裝置憑證均拒；`test_disabled_routes_and_redacted_errors` 驗 flagoff 不發送；`test_limits_survive_restart`、`test_stale_cancel_create_http_order` 驗限流及競爭。Worker 測試斷言 cron=`*/5 * * * *`、固定 POST URL、空 body、redirect=error、fetch 入口 404、錯誤不洩密。
- [x] **Step 2 — 跑 RED：** `python -m pytest tests/test_push_api.py -q`、`node tests/push_worker_check.cjs`。
- [x] **Step 3 — 接線：** Cookie 名 nkust_push_device、Path=/api/push、HttpOnly、SameSite=Strict，正式 Secure、測試 localhost 才可關 Secure；400 天到期。限制 body 16KiB、endpoint 4096 字元、auth 解碼 16 bytes、p256dh 解碼 65 bytes。公開 config 不解析 Google session。test 通知排入同一 dispatcher，重送 operation_id 不重複；內部執行用 threadpool 不阻塞事件迴圈。Worker 150 秒上限，只固定正式 Render origin 與內部路徑，secret 來自環境，不傳 DB／Gmail／VAPID 私鑰。忙碌安全回覆，失敗記 safe code，不在 Worker 自動重送模糊請求。
- [x] **Step 4 — 跑 GREEN：** 上述、既有公開 API／web auth 測試全過；超限回 429 並保留本機使用能力；確認內部路徑不依賴學生裝置 cookie。
- [x] **Step 5 — Commit：** `feat: expose isolated push APIs and cron trigger`。Worker 只建立檔案，不部署、不建立秘密。

## Task 5: IndexedDB v3 原子 outbox 與舊資料保存

**Files:** 修改 `app/static/web/todo-store.js`、`action-card-store.js`；新增 `push-store.js`、`tests/push_store_check.cjs`、`tests/browser/push_store_harness.js`、`push_store.html`；擴充既有 todo browser harness。

**Interfaces:** `PushStore.setIntent({sourceRef, intent, expectedRevision})->Promise<LocalReminder>`；`PushStore.flush({api, epoch})->Promise<SyncSummary>`；`PushStore.read(sourceRef)->Promise<LocalReminder|null>`。LocalReminder 包含本機 todo UUID、epoch、client_revision、server_revision、confirmed intent、sync state；不改既有 todo schema_version=1。API adapter 使用任務 4 契約。

- [x] **Step 1 — RED 測試：** `test_v2_upgrade_preserves_cards_and_todos` 驗 v2 資料升 v3；`test_abort_rolls_back_todo_and_cancel` 驗完成交易中止時兩者同撤回；`test_offline_complete_queues_cancel_atomically` 驗離線完成留下待同步取消；`test_old_epoch_does_not_flush`、`test_cancel_overtakes_inflight_create` 驗換裝置及舊請求。無 opt-in、私人、示範資料斷言網路請求數為 0。
- [x] **Step 2 — 跑 RED：** `node tests/push_store_check.cjs`，另以既有瀏覽器 harness 方法執行真實 IndexedDB 測試；不能只靠文字契約檢查。
- [x] **Step 3 — 實作交易：** 所有 DB opener 同步升 version=3，增加 pushBindings／pushOutbox。`TodoStore.change` 在同一交易寫 publicTodos、binding 和取消 outbox；未啟用提醒不建立 outbox。以 source_ref 合併最新意圖、保留 operation_id、client_revision 與 epoch；flush 只有伺服器確認才清除對應版本。較晚回覆不能清掉較新取消。稍後操作不重排截止提醒。處理 blocked／versionchange、quota、兩分頁及 tombstone，不刪舊 stores。
- [x] **Step 4 — 跑 GREEN：** Node 與真實 IndexedDB harness 全過，重跑 todo_store_check、現有 action-card-store 驗收；斷線顯示待同步而非取消成功。先製備 v3 相容回復程式，驗它可讀既有 v2 與升級後 v3。
- [x] **Step 5 — Commit：** `feat: persist atomic local reminder outbox`。

## Task 6: 推播操作介面、可見通知及公務待辦入口

**Files:** 新增 push-client.js、push-ui.js、push_controls.html、`tests/push_client_check.cjs`、`test_push_pages.py`；修改 todos.js、device_todos.html、office_mail_detail.html、對應 `app/web.py` 路由資料、sw.js、必要 CSS 與既有 pwa_worker_check.cjs。

**Interfaces:** `PushClient.prepare()->Promise<PushCapability>` 預先準備公鑰／SW；`PushClient.subscribeFromClick()->Promise<DeviceState>` 在 click 直接呼叫 browser subscribe；`PushUI.mount({store,client,root})->void`；Service Worker 消費 `{id,title,path,expires_at,kind}`，path 只接受兩種既有公開詳情路由。

- [x] **Step 1 — RED 測試：** `test_subscription_called_before_any_network_await` 驗 iOS 手勢；`test_browser_grant_server_failure_is_incomplete` 驗不能假啟用；`test_office_compact_todo_without_action_card` 驗公務僅小型加入待辦／截止入口；`test_push_visible_and_click_safe` 驗 showNotification、tag、過期與非同源跳轉拒絕。涵蓋 loading／empty／denied／unsupported／offline 狀態。
- [x] **Step 2 — 跑 RED：** `node tests/push_client_check.cjs`、`node tests/pwa_worker_check.cjs`、`python -m pytest tests/test_push_pages.py -q`。
- [x] **Step 3 — 實作互動：** 待辦加入保持免登入／預設不上傳；明確按開啟才展示最少保存說明、截止依據與確認。公務截止沿用既有解析器和 public_source，不恢復完整行動卡；沒有可靠截止允許標示「我自行確認」填入。提醒狀態區分待同步、已排程、需核對、服務接受、結果不明；提供取消單筆／全部、測試通知及稍後不變動提醒的說明。iPhone 未 standalone 時阻擋訂閱並說明前提。後端失敗保留 incomplete，未授權不重複彈窗；cookie 遺失要求明確重設訂閱，不認領別人端點。SW 顯示可見通知，使用固定 tag 與同源已驗證路徑開啟／聚焦公告；不快取私人資料或加靜默計時器。
- [x] **Step 4 — 跑 GREEN：** 上述及既有待辦／公告頁／來源隔離測試全過；用手機尺寸驗按鈕、日期確認與回公告。透過替身確認完整 card、私人內容與修正文字沒有離開裝置。
- [x] **Step 5 — Commit：** `feat: add opt-in deadline push controls`。此時推播核心完成，仍不宣稱正式 iPhone 已驗收。

## Task 7: 加入主畫面引導

**Files:** 新增 install-guide.js、install_guide.html、`tests/install_guide_check.cjs`；修改既有共用頁框接線與必要 CSS，沿用 manifest、圖示。

**Interfaces:** `InstallGuide.mount({root, window, storage})->void`；只有使用者點擊才呼叫 beforeinstallprompt 保留事件的 prompt；dismiss 狀態僅存本機、不等於已安裝。

- [x] **Step 1 — RED 測試：** `test_iphone_safari_steps` 驗分享→加入主畫面→新增→從圖示開啟；`test_standalone_no_repeat_prompt` 驗已安裝狀態；`test_ipad_desktop_ua_touch_detected` 驗 iPad 偽桌面 UA；`test_no_install_api_falls_back_to_menu` 驗無假安裝成功。Safari 與主畫面不同儲存時不自動搬移待辦。
- [x] **Step 2 — 跑 RED：** `node tests/install_guide_check.cjs`。
- [x] **Step 3 — 實作引導：** 一般學生免登入可見加入主畫面入口，依能力／standalone 呈現步驟，拒絕或略過仍可瀏覽。不能以 iOS UA 單獨宣稱支援；能力不足時顯示最低系統與瀏覽器條件。說明主畫面待辦若不同，需要從公告重新加入，不能偷偷雲端搬移。
- [x] **Step 4 — 跑 GREEN：** 引導、PWA 及既有導覽檢查通過，手機／桌面截圖人工檢查；不新增登入門檻或額外配色。
- [x] **Step 5 — Commit：** `feat: guide home screen installation for push`。

## Task 8: 獨立驗收、相容回復與正式啟用

**Files:** 新增 `docs/device-push-validation-2026-11-08.md`、`docs/device-push-operations.md`、`scripts/verify-push-postgresql.ps1`；必要時修正本期檔案，正式設定只在驗收後進行。

**Interfaces:** 驗收報告列版本、DB revision、每項實際結果／未測原因、相容回復 commit、flag 與 cron 狀態；維運流程不得記入任何秘密。實際日期若跨日更新報告日期，不偽造 11/08 已驗收。

- [x] **Step 1 — 建立可失敗驗收：** 測試腳本連獨立 PostgreSQL，拒絕正式 DB／未明確測試標記，任何 PG skip 視驗收失敗；涵蓋 0010→0011 保留資料、雙 worker、限流、裝置隔離、公開同步角色拒存取、v3 回復可讀。實機表列 iPhone 主畫面、桌面／Android 明確授權、關頁接收、撤銷、取消、點擊回公告；尚未操作先標未驗證。
- [x] **Step 2 — 記錄基線：** 原有 Python 全套、全部既有 .cjs 與新測試；環境失敗先處理，不能將 skip 列通過。核對無意改動 Gmail／OAuth／GitHub 公告排程。
- [x] **Step 3 — 完成本機與獨立驗收：** `python -m pytest -q`、每個 `tests/*check.cjs`、真實 IndexedDB harness、`scripts/verify-push-postgresql.ps1` 均保存摘要。執行專案要求的全變更 review，修正後只重跑受影響與必要回歸；不以靜態測試替代 iPhone 實機。
- [ ] **Step 4 — 有序啟用與觀察：** 先備份並驗還原／0011 加法遷移與 v3 相容回復版本；在正式操作前確認既有授權適用及必要當下安全確認。先關閉 flag 部署；檢查原公告與來源管理者收錄正常。由本人完成新憑證輸入儲存；確認 Cloudflare 免費方案、Render 同工作區 750 小時額度與費用限制後才啟用 cron。至少觀察兩次真正 scheduled run 和明確測試通知；由使用者在 iPhone 實機完成授權／關頁接收，不以服務 accepted 代替。缺權限、實機或額度時如實停在對應門檻。回復需關閉 flag／cron，持久停用未送工作後使用 schema0011／IDBv3 相容程式；重新啟用前重新核對提醒，不讓舊工作復活。
- [ ] **Step 5 — Commit／交付：** `docs: record device push validation and operations`。報告分列本機完成、獨立 PG、部署、真 cron、裝置實測；未完成任一不得宣稱整體完成。保留秘密與私有郵件隔離。

## 函式庫核對依據與自審

pywebpush 2.5.0 公開介面已從發行來源核對：`webpush` 支援 requests_session／ttl／timeout；HTTP 呼叫使用 session.post。來源 commit `7c2e75fcd6e1b9b8dc75d09cbc06373fae09c184`，見 [官方程式](https://github.com/web-push-libs/pywebpush/blob/7c2e75fcd6e1b9b8dc75d09cbc06373fae09c184/pywebpush/__init__.py) 及 [PyPI](https://pypi.org/project/pywebpush/)。VAPID 使用函式庫公開入口傳私鑰；安裝時核對 Python／cryptography 相容，不能為解依賴任意降版既有安全套件。

已自行逐項比對核准規格：八任務涵蓋日期、匿名隔離、持久取消、限流、端點傳輸、工作語義、公務待辦、iPhone 手勢、安裝與正式門檻。五項 Review Focus 均有具名測試；共用型別及 API 用語一致。補強 v3 原子交易與相容回復，避免僅靠提交後 JS callback 取消。文件為計畫，所有 checkbox 尚未執行；沒有修改產品程式、正式資料庫或服務設定。下一步由使用者審閱本計畫，確認後沿用本對話內逐任務實作。
