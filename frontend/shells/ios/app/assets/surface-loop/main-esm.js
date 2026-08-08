import { tag, log } from "./util-esm.js";
const j = (v) => {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
};
log(`esm-static ok (${tag})`, "ok");
try {
  const dyn = await import("./dyn-esm.js");
  log(`esm-dynamic ok (${dyn.dynTag})`, "ok");
} catch (e) {
  log(`esm-dynamic FAIL ${e}`, "fail");
}
log(`origin ${location.origin} secureContext=${window.isSecureContext}`);
try {
  const n = Number(localStorage.getItem("bootCount") ?? "0") + 1;
  localStorage.setItem("bootCount", String(n));
  log(`localStorage bootCount=${n} (origin ${location.origin})`, "ok");
} catch (e) {
  log(`localStorage FAIL ${e}`, "fail");
}
try {
  const db = await new Promise((res, rej) => {
    const r = indexedDB.open("probe", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("kv");
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
  const count = await new Promise((res, rej) => {
    const tx = db.transaction("kv", "readwrite");
    const st = tx.objectStore("kv");
    st.put(Date.now(), `boot-${Date.now()}`);
    const c = st.count();
    c.onsuccess = () => res(c.result);
    tx.onerror = () => rej(tx.error);
  });
  log(`indexedDB ok, rows=${count}`, "ok");
} catch (e) {
  log(`indexedDB FAIL ${e}`, "fail");
}
log(`document.cookie "${document.cookie}"`);
try {
  const r = await fetch("/probe/echo", { headers: { "x-probe": "hi" } });
  log(`fetch same-origin ${r.status} ${j(await r.json())}`, "ok");
} catch (e) {
  log(`fetch same-origin FAIL ${e}`, "fail");
}
try {
  const r = await fetch("https://postman-echo.com/get?probe=1", { signal: AbortSignal.timeout(8000) });
  const body = await r.json();
  log(`fetch external-https-cors ${r.status} origin-header-sent=${j(body.headers?.origin ?? "(none)")}`, "ok");
} catch (e) {
  log(`fetch external-https-cors FAIL ${e}`, "fail");
}
try {
  const r = await fetch("https://www.apple.com/library/test/success.html", { mode: "no-cors", signal: AbortSignal.timeout(8000) });
  log(`fetch external-https-nocors ok type=${r.type}`, "ok");
} catch (e) {
  log(`fetch external-https-nocors FAIL ${e}`, "fail");
}
try {
  const r = await fetch("https://api.github.com/zen", { signal: AbortSignal.timeout(8000) });
  log(`fetch external-https-cors2(github) ${r.status} "${(await r.text()).slice(0, 40)}"`, "ok");
} catch (e) {
  log(`fetch external-https-cors2(github) FAIL ${e}`, "fail");
}
try {
  const r = await fetch("http://neverssl.com/", { mode: "no-cors", signal: AbortSignal.timeout(8000) });
  log(`fetch external-http UNEXPECTED-OK type=${r.type}`, "fail");
} catch (e) {
  log(`fetch external-http blocked (${e}) — ATS holds`, "ok");
}
if ("serviceWorker" in navigator) {
  try {
    const reg = await navigator.serviceWorker.register("/sw.js");
    log(`serviceWorker registered scope=${reg.scope}`, "ok");
  } catch (e) {
    log(`serviceWorker present but register FAIL ${e}`, "fail");
  }
} else {
  log("serviceWorker API absent", "fail");
}
try {
  const ctl = new AbortController;
  const t0 = performance.now();
  const r = await fetch("/probe/stream", { signal: ctl.signal });
  const reader = r.body.getReader();
  const dec = new TextDecoder;
  let chunks = 0;
  while (chunks < 3) {
    const { value, done } = await reader.read();
    if (done)
      break;
    chunks++;
    log(`stream chunk ${chunks} +${Math.round(performance.now() - t0)}ms "${dec.decode(value).trim()}"`);
  }
  ctl.abort();
  log(`stream read ${chunks} chunks then aborted client-side`, "ok");
} catch (e) {
  log(`stream FAIL ${e}`, "fail");
}
try {
  await new Promise((res, rej) => {
    const ws = new WebSocket(`ws://${location.host}/probe/ws`);
    let got = 0;
    const t0 = performance.now();
    ws.onopen = () => ws.send("hello-from-surface");
    ws.onmessage = (ev) => {
      got++;
      log(`ws msg ${got} +${Math.round(performance.now() - t0)}ms "${ev.data}"`);
      if (got >= 4) {
        ws.close();
        res();
      }
    };
    ws.onerror = () => rej(new Error("ws error"));
    setTimeout(() => rej(new Error("ws timeout")), 8000);
  });
  log("websocket ok", "ok");
} catch (e) {
  log(`websocket FAIL ${e}`, "fail");
}
log("all-done");
