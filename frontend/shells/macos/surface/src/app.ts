// The surface. Framework-free; a ~15-line reactive helper is enough for this scope.
import { bridge, type CaptureStatusEvent } from "./bridge.generated.ts";

type State = {
  status: CaptureStatusEvent;
  settingKey: string;
  settingValue: string;
  log: string[];
};

const state: State = {
  status: { sessionId: null, state: "idle", elapsedMs: 0, levelDb: -60 },
  settingKey: "capture.sampleRateHz",
  settingValue: "—",
  log: [],
};

let scheduled = false;
function commit(mutate: (s: State) => void): void {
  mutate(state);
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => {
    scheduled = false;
    render();
  });
}
const log = (line: string) =>
  commit((s) => {
    s.log = [`${new Date().toLocaleTimeString()}  ${line}`, ...s.log].slice(0, 60);
  });

// Surface-side error beacon: WKWebView has no console you can read from a script.
window.addEventListener("error", (e) => {
  void fetch("/__selftest", { method: "POST", body: JSON.stringify({ probe: "error", message: String(e.message), source: e.filename, line: e.lineno }) });
});
window.addEventListener("unhandledrejection", (e) => {
  void fetch("/__selftest", { method: "POST", body: JSON.stringify({ probe: "rejection", reason: String((e as PromiseRejectionEvent).reason) }) });
});

const root = document.getElementById("root")!;
const modeEl = document.getElementById("mode")!;

function render(): void {
  const st = state.status;
  const level = Math.max(0, Math.min(100, ((st.levelDb + 60) / 60) * 100));
  document.querySelector(".dot")!.className = `dot${st.state === "recording" ? " recording" : ""}`;
  root.innerHTML = `
    <section class="card">
      <h2>Native calls</h2>
      <div class="row"><button id="start">startCapture</button>
        <button class="secondary" id="open">openExternal</button></div>
      <div class="row"><input id="key" value="${state.settingKey}" spellcheck="false" />
        <button class="secondary" id="read">readSetting</button></div>
      <div class="row"><span style="color:var(--muted)">value:</span> <b>${state.settingValue}</b></div>
      <h2 style="margin-top:16px">captureStatus (native → ui)</h2>
      <div class="row"><b>${st.state}</b> <span style="color:var(--muted)">${st.sessionId ?? "no session"} · ${(st.elapsedMs / 1000).toFixed(1)}s</span></div>
      <div class="meter"><i style="width:${level.toFixed(0)}%"></i></div>
      <h2 style="margin-top:16px">Native-feel probe</h2>
      <div style="color:var(--muted)">Try <kbd>Cmd</kbd><kbd>C</kbd>/<kbd>V</kbd> in the field, <kbd>Cmd</kbd><kbd>R</kbd>,
      two-finger scroll below, <kbd>Tab</kbd> focus ring.</div>
      <div class="scroller">${Array.from({ length: 60 }, (_, i) => `<p>momentum scroll row ${i + 1}</p>`).join("")}</div>
    </section>
    <section class="card">
      <h2>Event log</h2>
      <div class="log">${state.log.map((l) => `<div>${l}</div>`).join("") || "<div>—</div>"}</div>
    </section>`;

  root.querySelector<HTMLButtonElement>("#start")!.onclick = async () => {
    try {
      const r = await bridge.startCapture({ deviceId: "omi-devkit-2", sampleRateHz: 16000 });
      log(`startCapture → ${r.sessionId} (${r.state})`);
    } catch (e) {
      log(`startCapture failed: ${(e as Error).message}`);
    }
  };
  root.querySelector<HTMLButtonElement>("#read")!.onclick = async () => {
    const key = root.querySelector<HTMLInputElement>("#key")!.value;
    try {
      const r = await bridge.readSetting({ key });
      commit((s) => {
        s.settingKey = key;
        s.settingValue = r.value ?? "(unset)";
      });
      log(`readSetting(${key}) → ${r.value ?? "null"}`);
    } catch (e) {
      log(`readSetting failed: ${(e as Error).message}`);
    }
  };
  root.querySelector<HTMLButtonElement>("#open")!.onclick = async () => {
    try {
      const r = await bridge.openExternal({ url: "https://omi.me" });
      log(`openExternal → ${r.opened}`);
    } catch (e) {
      log(`openExternal failed: ${(e as Error).message}`);
    }
  };
}

bridge.on("captureStatus", (p) => commit((s) => { s.status = p; }));

/// `?selftest=1` round-trips every contract message and POSTs the result to the
/// dev server, so the bridge can be verified headlessly from a script.
async function selfTest(): Promise<void> {
  const results: Record<string, unknown> = { probe: "selftest", bridgeAvailable: bridge.available, visibility: document.visibilityState, hasFocus: document.hasFocus(), ua: navigator.userAgent.slice(0, 40) };
  try {
    results.startCapture = await bridge.startCapture({ deviceId: "selftest", sampleRateHz: 16000 });
    results.readSetting = await bridge.readSetting({ key: "capture.sampleRateHz" });
    results.readSettingMissing = await bridge.readSetting({ key: "does.not.exist" });
    results.openExternalRejectsNonHttps = await bridge.openExternal({ url: "file:///etc/passwd" });
    results.captureStatusEvent = await new Promise((res, rej) => {
      const off = bridge.on("captureStatus", (p) => { off(); res(p); });
      setTimeout(() => rej(new Error("no captureStatus within 4s")), 4000);
    });
  } catch (e) {
    results.error = (e as Error).message;
  }
  results.memory = (performance as any).memory?.usedJSHeapSize ?? null;
  await fetch("/__selftest", { method: "POST", body: JSON.stringify(results) });
}
if (location.search.includes("selftest")) void selfTest();

/// `?perf=1` measures scroll frame pacing + platform capability support and beacons it.
function perfProbe(): void {
  const sc = document.querySelector<HTMLElement>(".scroller")!;
  const frames: number[] = [];
  let last = performance.now();
  let n = 0;
  const step = (): void => {
    const t = performance.now();
    frames.push(t - last);
    last = t;
    sc.scrollTop += 12;
    if (++n < 120) return void requestAnimationFrame(step);
    frames.shift();
    const s = [...frames].sort((a, b) => a - b);
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    const paint = performance.getEntriesByType("paint")[0];
    void fetch("/__selftest", {
      method: "POST",
      body: JSON.stringify({
        probe: "nativefeel",
        appRegionDrag: CSS.supports("-webkit-app-region", "drag"),
        prefersDark: matchMedia("(prefers-color-scheme: dark)").matches,
        backdropFilter: CSS.supports("backdrop-filter", "blur(20px)"),
        overscrollBehavior: CSS.supports("overscroll-behavior", "contain"),
        systemFont: getComputedStyle(document.body).fontFamily.slice(0, 22),
        dpr: devicePixelRatio,
        frames: frames.length,
        medianFrameMs: +s[Math.floor(s.length / 2)].toFixed(2),
        p95FrameMs: +s[Math.floor(s.length * 0.95)].toFixed(2),
        over20ms: frames.filter((f) => f > 20).length,
        scrolled: sc.scrollTop,
        firstPaintMs: paint ? +paint.startTime.toFixed(1) : null,
        domInteractiveMs: nav ? +nav.domInteractive.toFixed(1) : null,
        loadEventMs: nav ? +nav.loadEventEnd.toFixed(1) : null,
      }),
    });
  };
  requestAnimationFrame(step);
}
modeEl.textContent = bridge.available ? "(native shell)" : "(plain browser — bridge unavailable)";
log(bridge.available ? "bridge ready" : "no native bridge; UI-only mode");
render();
// perf probe must run after the first render, so .scroller exists.
if (location.search.includes("perf")) perfProbe();
