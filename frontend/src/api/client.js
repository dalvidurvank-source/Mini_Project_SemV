const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let csrf='';
export const apiUrl=path=>`${base}/api${path}`;
export async function request(path, { signal, body, method } = {}) {
  let response;
  const timeout = new AbortController();
  const timeoutSeconds=path==='/listing-estimate'?180:120;
  const timer = setTimeout(() => timeout.abort(), timeoutSeconds*1000);
  const combined = signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal;
  try {
    response = await fetch(apiUrl(path), { credentials:'include', signal:combined, method:method || (body ? 'POST' : 'GET'), headers:{'X-Agrolink-Client':'1',...(body?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{})}, ...(body ? { body: JSON.stringify(body) } : {}) });
  } catch (error) {
    if (error.name === 'AbortError' && signal?.aborted) throw error;
    if (error.name === 'AbortError') throw new Error(`AgroLink took longer than ${timeoutSeconds} seconds. Retry the request; your entries are preserved.`);
    throw new Error('Cannot reach AgroLink. Check your connection and that the backend is running, then retry. Your entries are preserved.');
  } finally { clearTimeout(timer); }
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Please retry.'); }
  if (!response.ok) {const e=new Error(data.message || 'The request could not be completed. Please retry.');e.status=response.status;throw e;}
  if (Object.prototype.hasOwnProperty.call(data,'csrf')) csrf=data.csrf;
  return data;
}


