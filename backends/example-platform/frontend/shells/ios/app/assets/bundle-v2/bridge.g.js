export const BRIDGE_CONTRACT_VERSION = "0.2.0";

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
export const bridge = new OmiShellBridge;
