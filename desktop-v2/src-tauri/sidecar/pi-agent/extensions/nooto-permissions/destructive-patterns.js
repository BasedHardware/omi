/**
 * Standalone module exporting DESTRUCTIVE_RE as a plain JS CommonJS/ESM value.
 *
 * This mirrors the regex defined in index.ts verbatim so that:
 *   1. index.test.js can import it without TypeScript tooling.
 *   2. A single definition is authoritative — any drift between this file
 *      and index.ts is a test failure waiting to happen (see DUPLICATION NOTE
 *      in index.test.js).
 *
 * When the regex in index.ts changes, update this file to match, then re-run:
 *   cd src-tauri/sidecar/pi-agent && node --test ./extensions/nooto-permissions/index.test.js
 */

export const DESTRUCTIVE_RE = new RegExp(
  [
    String.raw`\brm\s+(-\S*r\S*f|-\S*f\S*r)\b`,
    String.raw`\brm\s+--[a-z-]*recursive`,
    String.raw`\bgit\s+push\b.*\s(-f|--force)\b`,
    String.raw`\bgit\s+push\b.*\s--force-with-lease\b`,
    String.raw`\bgit\s+reset\s+--hard\b`,
    String.raw`>\s*\/(?!tmp\/|tmp$)[^\s]`,
    String.raw`\bdd\s+if=`,
    String.raw`\bmkfs\.`,
    String.raw`:\(\)\s*\{.*:\|:.*&.*\}`,
    String.raw`:\s*\(\s*\)\s*\{`,
  ].join("|"),
);
