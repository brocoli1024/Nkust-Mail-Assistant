'use strict';
const $ = (id) => document.getElementById(id);
const state = {view: 'all', category: '', q: '', page: 1, pageSize: 20, request: 0};
let localBusy = false;
const titles = {all: '全部公告', today: '今日收到', deadline: '即將截止', action: '需要處理', jobs: '就業／實習', tech: 'AI／科技'};
const receivedFormat = new Intl.DateTimeFormat('zh-TW', {timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit'});
const timeFormat = new Intl.DateTimeFormat('zh-TW', {timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '資料讀取失敗，請稍後重試。');
  return data;
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function safeLink(url) {
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}
async function summary() {
  const data = await api('/api/summary');
  $('today-date').textContent = data.today.replaceAll('-', ' / ') + ' · 台北';
  $('today-count').textContent = data.today_received;
  $('total-count').textContent = data.total;
  $('deadline-count').textContent = data.upcoming_deadlines;
  $('action-count').textContent = data.action_unknown && !data.requires_action ? '—' : data.requires_action;
  $('action-note').textContent = data.action_unknown ? `${data.action_unknown} 則尚未判定` : '則公告需要採取行動';
  $('sync-status').textContent = (data.last_processed_at ? `最近成功處理：${timeFormat.format(new Date(data.last_processed_at))}` : '尚未同步郵件，按「同步 Gmail」開始。') + (data.failed_emails ? ` · ${data.failed_emails} 封郵件上次處理有錯誤` : ' · Gmail 唯讀');
}
async function loadList() {
  const request = ++state.request;
  $('announcements').setAttribute('aria-busy', 'true');
  $('announcements').replaceChildren(node('div', '正在讀取公告…', 'empty'));
  $('prev').disabled = $('next').disabled = true;
  showError('');
  const query = new URLSearchParams({view: state.view, page: state.page, page_size: state.pageSize});
  if (state.category) query.set('category', state.category);
  if (state.q) query.set('q', state.q);
  try {
    const data = await api('/api/announcements?' + query);
    if (request !== state.request) return;
    $('results-count').textContent = `共 ${data.total} 則公告`;
    document.querySelector('.list-heading > span:last-child').textContent = state.view === 'deadline' ? '依截止日期排序' : '依收件時間排序';
    const container = $('announcements'); container.replaceChildren();
    if (!data.items.length) {
      const empty = node('div', undefined, 'empty');
      empty.append(node('strong', '這裡暫時沒有公告'));
      empty.append(node('span', state.view === 'action' ? '行動需求尚待分析；你仍可查看全部公告與原文。' : '試試其他分類、清除搜尋，或同步更多郵件。'));
      container.append(empty);
    }
    for (const item of data.items) {
      const card = node('article', undefined, 'announcement');
      const content = node('div');
      const meta = node('div', undefined, 'meta');
      meta.append(node('span', item.category || item.source_category || '未分類', 'badge'), node('span', item.department));
      if (item.received_at) meta.append(node('span', receivedFormat.format(new Date(item.received_at)) + ' 收到'));
      const title = node('button', item.title, 'title-button');
      title.addEventListener('click', () => openDetail(item.id));
      content.append(meta, title);
      if (item.summary) content.append(node('div', 'AI 摘要 · ' + item.summary, 'row-note'));
      if (item.analysis_status === 'completed') meta.append(node('span', 'AI 已整理', 'ai-badge'));
      if (item.analysis_status === 'failed') meta.append(node('span', '分析未完成'));
      if (item.event_date || item.date_inferred) content.append(node('div', [item.event_date ? `活動 ${item.event_date}` : '', item.date_inferred ? '部分日期年份依收件年補足' : ''].filter(Boolean).join(' · '), 'row-note'));
      card.append(content);
      if (item.deadline) card.append(node('span', `截止 ${item.deadline}`, 'deadline-tag'));
      container.append(card);
    }
    const pages = Math.max(1, Math.ceil(data.total / state.pageSize));
    $('page-label').textContent = `第 ${state.page} / ${pages} 頁`;
    $('prev').disabled = state.page <= 1;
    $('next').disabled = state.page >= pages;
  } catch (error) {
    if (request !== state.request) return;
    $('announcements').replaceChildren();
    $('results-count').textContent = '讀取未完成';
    showError(error.message);
  } finally {
    if (request === state.request) $('announcements').setAttribute('aria-busy', 'false');
  }
}
let detailRequest = 0;
let detailItem = null;
$('detail').append($('web-controls').content.cloneNode(true));
async function openDetail(id) {
  const request = ++detailRequest;
  $('detail-title').textContent = '載入中…';
  $('detail-meta').textContent = $('detail-dates').textContent = $('detail-text').textContent = '';
  $('detail-ai').replaceChildren();
  detailItem = null;
  $('scrape-one').disabled = $('analyze-one').disabled = true;
  $('web-message').textContent = '';
  $('web-text').textContent = ''; $('web-text').hidden = true;
  $('detail-link').hidden = true;
  if (!$('detail').open) $('detail').showModal();
  try {
    const item = await api('/api/announcements/' + id);
    if (request !== detailRequest) return;
    detailItem = item;
    $('scrape-one').disabled = localBusy || !item.url;
    $('analyze-one').disabled = localBusy || !item.web?.text || item.analysis_status === 'completed';
    $('scrape-one').textContent = item.web?.text ? '重新擷取網頁' : '擷取網頁';
    $('web-message').textContent = item.web ? (item.web.error || `擷取完成：${timeFormat.format(new Date(item.web.fetched_at))} · 來源 ${item.web.url}`) : item.url ? '尚未擷取網頁內容。' : '此公告沒有網頁連結。';
    if (item.web?.text) { $('web-text').hidden = false; $('web-text').textContent = item.web.text; }
    $('detail-title').textContent = item.title;
    $('detail-meta').textContent = `${item.department} · ${item.source_category}`;
    $('detail-text').textContent = item.original_text;
    const box = $('detail-ai');
    if (item.analysis) {
      const analysis = item.analysis;
      if (item.analysis_status === 'pending') box.append(node('p', '已補充網頁內容，以下為先前分析結果；請重新分析這則公告。'));
      box.append(node('strong', analysis.status === 'failed' ? '上次分析未完成；如有既有結果，仍保留供參考。' : 'AI 整理 · 請搭配原文確認'));
      if (analysis.result) {
        const result = analysis.result;
        box.append(node('p', result.summary));
        box.append(node('p', `分類：${result.category} · 模型：${analysis.result_model}`));
        if (result.used_web_content) box.append(node('p', '本次分析已使用網頁補充內容。'));
        box.append(node('p', result.requires_action === null ? '行動需求：無法判定' : result.requires_action ? '行動需求：有可採取的行動，不代表你必須參加或符合資格。' : '行動需求：未辨識到需採取的行動。'));
        if (result.keywords.length) box.append(node('p', '關鍵字：' + result.keywords.join('、')));
        for (const [label, field] of [['行動依據', 'action_evidence'], ['活動日期依據', 'event_evidence'], ['截止日期依據', 'deadline_evidence']]) {
          if (result[field]) box.append(node('p', `${label}：「${result[field]}」`));
        }
      }
      if (analysis.warnings.length) box.append(node('p', '部分 AI 判斷缺少有效原文依據，已略過；請人工確認。'));
    } else box.append(node('p', '尚未進行 AI 分析。'));
    $('detail-dates').textContent = item.date_evidence.map(e => `${e.original_text} → ${e.iso_date || '待確認'}${e.year_inferred ? '（年份依收件年補足）' : ''}`).join('；');
    const url = safeLink(item.url);
    if (url) { $('detail-link').href = url; $('detail-link').hidden = false; }
  } catch (error) { if (request === detailRequest) $('detail-title').textContent = error.message; }
}
$('close-detail').addEventListener('click', () => $('detail').close());
async function detailAction(kind) {
  const item = detailItem;
  if (!item || localBusy) return;
  localBusy = true;
  for (const id of ['scrape-one', 'analyze-one', 'analyze', 'retry-ai', 'sync', 'sync-limit']) $(id).disabled = true;
  $('web-message').textContent = kind === 'scrape' ? '正在擷取公告網頁…' : '正在使用原文與網頁補充內容分析…';
  let message = '';
  try {
    const result = await api(kind === 'scrape' ? `/api/announcements/${item.id}/scrape` : '/api/ai/analyze', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'NKUST-Dashboard'},
      body: JSON.stringify(kind === 'scrape' ? {refresh: Boolean(item.web)} : {announcement_id: item.id, limit: 1, retry_failed: item.analysis_status === 'failed'})});
    message = kind === 'scrape' ? result.message || (result.changed ? '已補充網頁內容。可按「分析這則公告」更新摘要。' : '內容沒有變更。') : `分析完成 ${result.processed} 則，失敗 ${result.failed} 則。`;
    await Promise.all([summary(), loadList()]);
  } catch (error) { message = error.message; }
  finally {
    localBusy = false;
    $('sync').disabled = $('sync-limit').disabled = false;
    if ($('detail').open && detailItem?.id === item.id) {
      await openDetail(item.id);
      $('web-message').textContent = message;
    }
    refreshAI().catch(error => showError(error.message));
  }
}
$('scrape-one').addEventListener('click', () => detailAction('scrape'));
$('analyze-one').addEventListener('click', () => detailAction('analyze'));
$('detail').addEventListener('close', () => { detailRequest++; });
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  state.view = button.dataset.view; state.page = 1;
  $('view-title').textContent = titles[state.view];
  document.querySelectorAll('.nav-button').forEach(nav => {
    nav.classList.toggle('active', nav.dataset.view === state.view);
    nav.setAttribute('aria-pressed', String(nav.dataset.view === state.view));
  });
  loadList();
}));
$('category').addEventListener('change', () => { state.category = $('category').value; state.page = 1; loadList(); });
$('search').addEventListener('input', () => { $('clear-search').hidden = !$('search').value; });
$('clear-search').addEventListener('click', () => { $('search').value = ''; state.q = ''; state.page = 1; $('clear-search').hidden = true; $('search').focus(); loadList(); });
$('search-form').addEventListener('submit', event => { event.preventDefault(); state.q = $('search').value.trim(); state.page = 1; loadList(); });
$('prev').addEventListener('click', () => { state.page--; loadList(); });
$('next').addEventListener('click', () => { state.page++; loadList(); });
$('sync').addEventListener('click', async () => {
  localBusy = true;
  $('analyze').disabled = $('retry-ai').disabled = true;
  $('sync').disabled = true; $('sync-limit').disabled = true;
  $('sync').textContent = '同步中…';
  $('sync-status').textContent = '正在讀取 Gmail，請稍候；首次授權可能會開啟登入視窗。';
  try {
    const result = await api('/api/gmail/sync', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'NKUST-Dashboard'}, body: JSON.stringify({limit: Number($('sync-limit').value)})});
    state.page = 1;
    await Promise.all([summary(), loadList()]);
    $('sync-status').textContent = `同步結束 · 處理 ${result.processed} 封 · 略過 ${result.skipped} 封 · 寫入 ${result.announcements_written} 則公告 · 失敗 ${result.failed} 封` + (result.warnings.length ? ` · ${result.warnings.length} 則解析提醒` : '');
    if (result.failed) showError('部分郵件處理失敗，成功資料已保留。再次同步可重試；未知郵件版型需調整解析器。');
  } catch (error) { $('sync-status').textContent = '同步未完成'; showError(error.message); }
  finally { localBusy = false; $('sync').disabled = false; $('sync-limit').disabled = false; $('sync').textContent = '同步 Gmail'; refreshAI().catch(error => showError(error.message)); }
});
async function refreshAI() {
  const data = await api('/api/ai/status');
  $('ai-status').textContent = data.configured ? `iAI · ${data.model} ｜ 已完成 ${data.completed} 則 · 待分析 ${data.pending} 則 · 失敗 ${data.failed} 則` + (data.busy ? ' · 作業進行中，完成後可重新整理頁面。' : '') : '尚未設定完成，請填寫本機 iAI 金鑰與模型後重新啟動服務。';
  $('analyze').disabled = !data.configured || localBusy || data.busy;
  $('retry-ai').disabled = !data.configured || localBusy || data.busy || !data.failed;
}
async function analyzeBatch(retryFailed) {
  localBusy = true;
  $('analyze').disabled = $('retry-ai').disabled = $('sync').disabled = $('sync-limit').disabled = true;
  $('ai-message').textContent = '正在透過 iAI 分析，通常約 30–90 秒；關閉頁面不會取消已送出的分析。';
  try {
    const result = await api('/api/ai/analyze', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'NKUST-Dashboard'}, body: JSON.stringify({limit: 5, retry_failed: retryFailed})});
    state.page = 1;
    await Promise.all([summary(), loadList()]);
    $('ai-message').textContent = `分析結束 · 完成 ${result.processed} 則 · 失敗 ${result.failed} 則 · 資料變動略過 ${result.skipped} 則` + (result.warnings.length ? ' · 部分判斷需查看原文確認' : '') + (result.failed ? '。可稍後按「重試失敗項目」。' : '') + (!result.processed && !result.failed && !result.skipped ? '。目前沒有需處理的項目。' : '');
  } catch (error) { $('ai-message').textContent = error.message; }
  finally {
    localBusy = false;
    $('sync').disabled = $('sync-limit').disabled = false;
    refreshAI().catch(error => showError(error.message));
  }
}
$('analyze').addEventListener('click', () => analyzeBatch(false));
$('retry-ai').addEventListener('click', () => analyzeBatch(true));
Promise.all([summary(), loadList(), refreshAI()]).catch(error => { showError(error.message); });
