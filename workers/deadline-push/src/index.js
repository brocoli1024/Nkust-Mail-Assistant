// Fixed-purpose free cron. No database or mail credentials belong here.
const TARGET = 'https://nkust-mail-assistant.onrender.com/internal/push/run';
export default {
  async fetch() { return new Response('Not found', {status:404}); },
  async scheduled(event, env, ctx) {
    if (!env.NKUST_PUSH_TRIGGER_SECRET) { console.log('PUSH_TRIGGER_UNCONFIGURED'); throw new Error('PUSH_TRIGGER_UNCONFIGURED'); }
    try {
      const response = await fetch(TARGET, {method:'POST',redirect:'error',body:'',
        headers:{Authorization:'Bearer '+env.NKUST_PUSH_TRIGGER_SECRET},signal:AbortSignal.timeout(150000)});
      if (!response.ok) {
        // Only a bounded HTTP code is diagnostic; never log headers or response bodies.
        console.log(Number.isInteger(response.status) && response.status >= 100 && response.status <= 599
          ? 'PUSH_TRIGGER_HTTP_' + response.status : 'PUSH_TRIGGER_HTTP_UNKNOWN');
        throw new Error('PUSH_TRIGGER_FAILED');
      }
      console.log('PUSH_TRIGGER_OK');
    } catch { console.log('PUSH_TRIGGER_FAILED'); throw new Error('PUSH_TRIGGER_FAILED'); }
  }
};
