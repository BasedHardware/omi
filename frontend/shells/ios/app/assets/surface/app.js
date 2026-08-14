(() => {
  // surface/src/bridge.g.ts
  var BRIDGE_CONTRACT_VERSION = "0.2.0";

  class OmiShellBridge {
    #seq = 0;
    #pending = new Map;
    #subs = new Map;
    constructor() {
      window.__omiBridge = {
        __reply: (raw) => {
          const e = JSON.parse(raw);
          const p = this.#pending.get(e.id);
          if (!p)
            return;
          this.#pending.delete(e.id);
          e.ok ? p.resolve(e.result) : p.reject(new Error(e.error ?? "bridge error"));
        },
        __push: (raw) => {
          const e = JSON.parse(raw);
          for (const cb of this.#subs.get(e.method) ?? [])
            cb(e.params);
        }
      };
    }
    get available() {
      return typeof window.OmiBridge?.postMessage === "function";
    }
    #call(method, params) {
      const ch = window.OmiBridge;
      if (!ch)
        return Promise.reject(new Error("shell bridge unavailable (running outside the shell?)"));
      const id = "c" + ++this.#seq;
      return new Promise((resolve, reject) => {
        this.#pending.set(id, { resolve, reject });
        ch.postMessage(JSON.stringify({ id, method, params: params ?? null }));
      });
    }
    #subscribe(method, cb) {
      const list = this.#subs.get(method) ?? [];
      list.push(cb);
      this.#subs.set(method, list);
    }
    getDeviceState() {
      return this.#call("getDeviceState", undefined);
    }
    startListening(params) {
      return this.#call("startListening", params);
    }
    onTranscriptEvent(cb) {
      this.#subscribe("transcriptEvent", cb);
    }
  }
  var bridge = new OmiShellBridge;

  // surface/src/app.ts
  var $ = (id) => document.getElementById(id);
  var out = $("out");
  var benchOut = $("bench");
  var BUILD_STAMP = "2026-08-11 04:29:52Z";
  $("mode").textContent = `contract ${BRIDGE_CONTRACT_VERSION} · build ${BUILD_STAMP} · ` + `origin ${location.protocol}//${location.host || "assets"} · ` + `bridge ${bridge.available ? "attached" : "MISSING"}`;
  $("btn-device").addEventListener("click", async () => {
    const t0 = performance.now();
    try {
      const s = await bridge.getDeviceState();
      out.textContent = `getDeviceState -> ${JSON.stringify(s, null, 2)}
(${(performance.now() - t0).toFixed(1)} ms)`;
    } catch (e) {
      out.textContent = `error: ${e.message}`;
    }
  });
  $("btn-listen").addEventListener("click", async () => {
    try {
      const s = await bridge.startListening({ sampleRateHz: 16000, language: "en" });
      out.textContent = `startListening -> ${JSON.stringify(s)}`;
    } catch (e) {
      out.textContent = `error: ${e.message}`;
    }
  });
  $("btn-bench").addEventListener("click", async () => {
    benchOut.textContent = "running…";
    const N = 100;
    const samples = [];
    for (let i = 0;i < 10; i++)
      await bridge.getDeviceState();
    const wall0 = performance.now();
    for (let i = 0;i < N; i++) {
      const t0 = performance.now();
      await bridge.getDeviceState();
      samples.push(performance.now() - t0);
    }
    const wall = performance.now() - wall0;
    samples.sort((a, b) => a - b);
    const q = (p) => samples[Math.min(samples.length - 1, Math.floor(p * samples.length))];
    benchOut.textContent = `n=${N} round trips (ui->shell->ui)
` + `p50 ${q(0.5).toFixed(2)} ms
p95 ${q(0.95).toFixed(2)} ms
` + `min ${samples[0].toFixed(2)} ms · max ${samples[N - 1].toFixed(2)} ms
` + `wall ${wall.toFixed(0)} ms total · mean ${(wall / N).toFixed(2)} ms/call`;
    console.log("BENCH", benchOut.textContent.replace(/\n/g, " | "));
  });
  var transcript = $("transcript");
  var cleared = false;
  bridge.onTranscriptEvent((e) => {
    if (!cleared) {
      transcript.innerHTML = "";
      cleared = true;
    }
    const oneWay = Date.now() - e.shellSentAtMs;
    const div = document.createElement("div");
    div.className = "seg" + (e.isFinal ? "" : " partial");
    div.textContent = `${e.text}  (+${oneWay} ms shell→ui)`;
    transcript.appendChild(div);
    while (transcript.childElementCount > 8)
      transcript.removeChild(transcript.firstChild);
    console.log(`PUSH v2 oneway_ms=${oneWay}`);
  });
  if (location.protocol.startsWith("http")) {
    let seen = null;
    setInterval(async () => {
      try {
        const s = await (await fetch("/stamp", { cache: "no-store" })).text();
        if (seen === null)
          seen = s;
        else if (s !== seen) {
          console.log("LIVERELOAD");
          location.reload();
        }
      } catch {}
    }, 500);
  }
  (async () => {
    try {
      const r = await fetch("http://localhost:8787/stamp", { cache: "no-store" });
      console.log(`NETPROBE ok status=${r.status} origin=${location.protocol}`);
    } catch (e) {
      console.log(`NETPROBE blocked origin=${location.protocol} err=${e.message}`);
    }
  })();
  var filler = $("filler");
  for (let i = 0;i < 40; i++) {
    const d = document.createElement("div");
    d.className = "filler";
    d.textContent = `scroll row ${i + 1}`;
    filler.appendChild(d);
  }
})();
