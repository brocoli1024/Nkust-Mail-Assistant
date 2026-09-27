const connectivityStatus = document.querySelector('[data-connectivity-status]');

function updateConnectivityStatus() {
  if (connectivityStatus) connectivityStatus.hidden = navigator.onLine;
}

updateConnectivityStatus();
window.addEventListener('online', updateConnectivityStatus);
window.addEventListener('offline', updateConnectivityStatus);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(() => {
      // The website remains usable online if registration is unavailable.
    });
  });
}
