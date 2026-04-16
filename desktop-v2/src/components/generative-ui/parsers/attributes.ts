const ATTR_RE = /(\w[\w-]*)\s*=\s*"([^"]*)"/g;

export function parseAttributes(attrString: string): Record<string, string> {
  const out: Record<string, string> = {};
  let m: RegExpExecArray | null;
  while ((m = ATTR_RE.exec(attrString)) !== null) {
    out[m[1]] = m[2];
  }
  return out;
}
