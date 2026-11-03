'use strict';

(() => {
  const form = document.getElementById('announcement-filters');
  if (!form) return;
  const status = document.getElementById('filter-status');
  for (const select of form.querySelectorAll('select')) {
    select.addEventListener('change', () => form.requestSubmit());
  }
  form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    if (status) {
      status.hidden = false;
      status.textContent = '正在搜尋／更新清單，請稍候。';
    }
  });
  window.addEventListener('pageshow', () => {
    form.removeAttribute('aria-busy');
    if (status) {
      status.hidden = true;
      status.textContent = '';
    }
  });
})();
