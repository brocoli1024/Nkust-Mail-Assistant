'use strict';

const form = document.getElementById('announcement-filters');
for (const select of form.querySelectorAll('select')) {
  select.addEventListener('change', () => form.requestSubmit());
}
