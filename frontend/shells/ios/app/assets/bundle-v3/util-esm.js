export const tag = "util-esm-static-import";
export function log(msg, cls = "") {
  console.log(`PROBE ${msg}`);
  const el = document.createElement("div");
  el.textContent = msg;
  if (cls)
    el.className = cls;
  document.getElementById("log").appendChild(el);
}
