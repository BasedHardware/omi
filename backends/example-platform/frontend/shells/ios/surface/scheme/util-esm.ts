// Separate file on purpose: proves a real multi-file ESM graph resolves over
// the custom-scheme origin (static import in main-esm.ts).
export const tag = 'util-esm-static-import';

export function log(msg: string, cls = '') {
  console.log(`PROBE ${msg}`);
  const el = document.createElement('div');
  el.textContent = msg;
  if (cls) el.className = cls;
  document.getElementById('log')!.appendChild(el);
}
