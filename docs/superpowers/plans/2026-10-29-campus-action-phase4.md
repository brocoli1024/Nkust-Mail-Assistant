# 確認後下載ICS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，在本對話逐項實作；一次fresh全範圍審查，不派每項實作者。

**Goal:** 選擇活動或截止→核對日期與時間→下載可驗證的.ics，不冒稱已加入行事曆。

**Architecture:** server只映射最小卡片payload，browser共用純ICS序列化及DOM控制器，現有action-card/todo流程接入。沒有新下載路由或儲存。

**Tech Stack:** FastAPI/Jinja、原生JS/Intl/WebCrypto/Blob、pytest/Node。

**Spec:** docs/superpowers/specs/2026-10-29-campus-action-phase4-design.md

## Global Constraints

- 不部署、push、正式資料庫／OAuth／付費服務／新依賴；不實作第五階段合併。
- pending/stale日期不直接匯出，AI不唯一依據；只有supported/user_confirmed可在使用者再次確認後匯出。
- 活動與截止分開。無時間用全天；未解析時間須選擇方式或核對後手填，時間固定Asia/Taipei，不猜持續長度。
- 公開／私人／demo邊界沿用；private不存browser storage、不新增網路上傳；todo匯出加入時快照。
- 不修改公告／修正／待辦狀態。下載不等於加入行事曆。文字繁中、手機44px操作與錯誤可讀。

## Review Focus

1. 中文／emoji跨75bytes折行、CRLF屬性注入與URL控制字元不可破壞檔案（Task1）。
2. 台灣午夜換日、閏日／年底、全天exclusive end、歷史DST無唯一時間不可錯算（Task1）。
3. 匯出確認後改日期／來源卡或輸入未保存修正，不得下載舊確認（Task2）。
4. 私人待辦快照／換帳號／公開裝置資料不得互相混入，最小payload不含整封郵件（Task2）。
5. crypto/Blob/下載失敗與JS停用必須提示，不能宣稱已落盤或已匯入（Task2、3）。

## Task 1：最小payload及純ICS

**Files:** app/services/calendar_export.py、app/static/web/calendar-ics.js、tests/test_calendar_payload.py、tests/calendar_ics_check.cjs。

**Interfaces:** Python calendar_payload(card:ActionCard|dict,*,snapshot:bool=False)->dict；JS projectCard(card,{snapshot=false}={})同樣schema：{schema_version:1,source:{kind,source_ref,title,url},baseline_hash,summary,action,dates:{event_date,deadline}:{value,state,evidence:[str]},time_status,context:current|snapshot}。摘要160字，action1200，title500，日期依據最多5則每則2000字，無AI/完整segments/帳號。

JS validateSelection(payload,selection)->normalized；selection={kind:event_date|deadline,mode:all_day|timed,startTime:'HH:MM'|null,endDateTime:'YYYY-MM-DDTHH:MM'|null,confirmed:bool}。buildCalendar(payload,selection,{now=Date(),crypto=globalThis.crypto}={}):Promise<{text,filename}>。export foldLine/escapeText/taipeiToUTC 供測試。確認必須stricttrue，日期ISO有效／非pending，不猜年份；全天次日若超過四位年則拒絕。定時Intl Asia/Taipei解本地時間後輸出UTC，非唯一／不存在拒絕；end晚於start，空白則省略DTEND。

- [ ] 寫payload／Node測試，Expected缺模組RED。斷言不含原文segments／AI／email；pending拒絕、確認拒絕、分別日期、CRLF／UTF8折行完整、注入僅文字、來源安全URL、UTC換日／閏年、UID種別分離、private/demo命名。
- [ ] 實作映射與序列化；VEVENT含UID/DTSTAMP/DTSTART/SUMMARY/DESCRIPTION/URL(有安全來源時)，全天DTEND次日；固定PRODID/2.0/GREGORIAN；private CLASS:PRIVATE但無安全保證。
- [ ] pytest tests/test_calendar_payload.py 與 node tests/calendar_ics_check.cjs，Expected exit0；提交 feat: build confirmed calendar export files。

## Task 2：共用確認介面與接線

**Files:** app/static/web/calendar-controls.js、app/templates/web/calendar_controls.html、tests/test_calendar_pages.py；修改 api/session.py註冊Jinja helper、action_card.html、action-card.js、todos.js、todo_rows.html、六種含詳情或todo的頁面script、account.css。

**Interfaces:** NkustCalendarUI.setCard(actionCardNode,card)、setDirty(actionCardNode)、mount(parent,payload,{wait=false,dirty=false}={})。current public/demo預設wait，paint成功才設payload；private直接server最小payload，但編輯input或已回傳error停用。todo row mount(snapshotpayload)不讀當前修正。controller取消舊確認，crypto await後再次比對版本／選項，拒絕舊結果。

- [ ] 寫頁面RED：三詳情payload／script；private無裝置store、原文未混入最小payload；兩個owner隔離；私人todo snapshot／公開首頁載入；GET不寫庫，XSS跳脫。Expected缺UI RED。
- [ ] 元件包含種類select、日期／依據、全天／定時、start time、optional end datetime、Asia/Taipei、來源連結、確認checkbox、下載button、status及noscript。pending顯示修正指引，time_status=unparsed不預選模式；示範／私人／snapshot警語。所有input/change取消確認（確認checkbox本身除外）。
- [ ] Browser Blob下載固定檔名、延後revoke objectURL；成功只說啟動下載，無持久化／上傳／自動標完成；API不可用與驗證失敗保留輸入並清楚提示。
- [ ] 跑 calendar頁面及原action-card/todo/public/demo/PWA測試，Node新舊五項與syntax checks Expected exit0；提交 feat: confirm calendar downloads from cards and todos。

## Task 3：檔案驗收、全回歸與交付

**Files:** 合成browser harness/QA資料、README/privacy/public-announcements、docs/campus-action-phase4-validation-2026-10-29.md、本計畫。

- [ ] 真實browser：未確認無下載、pending阻擋、改選／修正重確認、全天/定時實際下載並檢查檔案、snapshot與current差別、private/demo警語；320/390px、焦點、錯誤，僅合成截圖。下載不測外部行事曆匯入。
- [ ] 完整pytest新basetemp、五項Node、diff --check；PG未設定如實skip。本階段無migration，REQUIRED_REVISION保持0008。
- [ ] 一次fresh整範圍唯讀審查；Critical/Important一輪RED→GREEN修正及全套回歸；minor裁定記錄延期，不派第二審。
- [ ] 文件標本機未部署、資料／下載界線及RFC驗證範圍；精確提交、保留工作區、不push；停止QA與清理本計畫scratch，先保存完整rulings/deferred。

Self-review：Task1 payload供Task2 Python/Jinja及JS動態卡；Task2在actioncard paint之後啟用防錯用原始值。todo用snapshot不自動升級日期。五項Review Focus各有負面測試／browser驗收；不以同意功能範圍代替證據。沿用使用者本對話inline及不需重核授權。
