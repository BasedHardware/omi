/**
 * CROSS-SIDE HOST-BRIDGE CHANNEL AGREEMENT
 * ========================================
 *
 * The defect class: each half of a host bridge can be individually correct
 * (same verb names, green unit tests) while the product is dead, because the
 * page posts to a WKScriptMessageHandler the shell never registers.
 *
 * Verb-name agreement is not enough — that is exactly what passed while
 * Rewind's capture controls rendered the unavailable bridge. This test reads
 * the REAL production host-socket modules and the REAL macOS shell sources
 * and requires the channel *transport* to agree: every CHANNEL the page
 * looks up must be a `static let channel` the shell both declares and
 * registers on `userContentController`, and every dedicated host-socket
 * channel the shell registers must be named by a host-socket module.
 *
 * red-proof: delete the `omiScreenBridge` registration in main.swift, or
 * rename CHANNEL in screen-host-socket.ts, and this fails. Matching dotted
 * verb names (`screen.start`) while the channel disagrees must still fail.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import { describe, test } from "node:test";

const { REPO_PATHS, assertCrossTreePairingIsDeclared, assertRepoPathsExist } =
  await import(new URL("../lib/provenance.mjs", import.meta.url).href);

assertRepoPathsExist();
assertCrossTreePairingIsDeclared();

const ROOT = REPO_PATHS.platform;
const HOST_SOCKET_DIR = join(ROOT, "frontend/packages/surfaces/src/production");
const SHELL_DIR = join(ROOT, "frontend/shells/macos/shell/Sources/OmiShell");
const MAIN_SWIFT = join(SHELL_DIR, "main.swift");

/** Shell channels that are not production host-socket modules. */
const GENERIC_SHELL_CHANNELS = new Set([
  "OmiShellBridge",
  "omiHttp",
  "omiStream",
  "omiChatAttachmentStaging",
  "omiConsole",
]);

function swiftFiles() {
  return readdirSync(SHELL_DIR)
    .filter((name) => name.endsWith(".swift"))
    .map((name) => ({ name, text: readFileSync(join(SHELL_DIR, name), "utf8") }));
}

function hostSocketFiles() {
  return readdirSync(HOST_SOCKET_DIR)
    .filter((name) => name.endsWith("host-socket.ts"))
    .map((name) => ({ name, text: readFileSync(join(HOST_SOCKET_DIR, name), "utf8") }));
}

function surfaceChannels(files) {
  const channels = new Map();
  for (const file of files) {
    const declared = file.text.match(/const CHANNEL = "([^"]+)"/);
    assert.ok(declared, `${file.name} must declare const CHANNEL = "..."`);
    const channel = declared[1];
    const looksUp =
      file.text.includes(`messageHandlers?.${channel}`)
      || file.text.includes("messageHandlers?.[CHANNEL]")
      || file.text.includes(`readonly ${channel}?`)
      || new RegExp(String.raw`messageHandlers\?\.${channel}`).test(file.text);
    assert.ok(
      looksUp,
      `${file.name} declares CHANNEL=${channel} but never looks it up on messageHandlers`,
    );
    assert.match(
      file.text,
      /action:\s*"|"action"|action,/,
      `${file.name} must post the host-socket {id, action} envelope, not the generic method dispatcher`,
    );
    channels.set(channel, file.name);
  }
  return channels;
}

function resolveIdentifier(text, identifier, visiting = new Set()) {
  if (visiting.has(identifier)) return null;
  visiting.add(identifier);
  const literal = text.match(
    new RegExp(String.raw`(?:static let|let) ${identifier} = "([^"]+)"`),
  );
  if (literal) return literal[1];
  const alias = text.match(
    new RegExp(String.raw`(?:static let|let) ${identifier} = ([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)`),
  );
  if (!alias) return null;
  return resolveIdentifier(text, alias[2], visiting);
}

function declaredShellChannels(files) {
  const allText = files.map((file) => file.text).join("\n");
  const declared = new Map();
  for (const file of files) {
    const typeRe = /(?:^|\n)(?:public |final |private |enum |struct |class )+(?:class|struct|enum) ([A-Za-z0-9_]+)/g;
    let typeMatch;
    const types = [];
    while ((typeMatch = typeRe.exec(file.text))) {
      types.push({ name: typeMatch[1], index: typeMatch.index });
    }
    const channelRe = /static let (channel|messageHandlerName|consoleHandlerName) = ([^\n]+)/g;
    let channelMatch;
    while ((channelMatch = channelRe.exec(file.text))) {
      const property = channelMatch[1];
      const rhs = channelMatch[2].trim();
      let value = null;
      const quoted = rhs.match(/^"([^"]+)"/);
      if (quoted) value = quoted[1];
      else {
        const ref = rhs.match(/^([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)/);
        if (ref) value = resolveIdentifier(allText, ref[2]);
      }
      if (!value || value === "1") continue;
      const owner = [...types].reverse().find((type) => type.index < channelMatch.index);
      if (!owner) continue;
      declared.set(`${owner.name}.${property}`, value);
      declared.set(value, owner.name);
    }
  }
  return declared;
}

function registeredChannels(mainText, declared) {
  const registered = new Map();
  const addRe =
    /userContentController\.add(?:ScriptMessageHandler)?\([\s\S]*?name:\s*(?:Self\.)?([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?)/g;
  let match;
  while ((match = addRe.exec(mainText))) {
    const ref = match[1];
    const value = declared.get(ref) ?? (ref.includes(".") ? null : declared.get(`WebViewController.${ref}`));
    assert.ok(value, `main.swift registers name:${ref} but that identifier does not resolve to a channel string`);
    registered.set(value, ref);
  }
  return registered;
}

describe("production host-socket channels are the channels the macOS shell registers", () => {
  const sockets = hostSocketFiles();
  const swift = swiftFiles();
  const mainText = readFileSync(MAIN_SWIFT, "utf8");
  const surface = surfaceChannels(sockets);
  const declared = declaredShellChannels(swift);
  const registered = registeredChannels(mainText, declared);

  test("every production host-socket CHANNEL is declared and registered by the macOS shell", () => {
    assert.ok(surface.size >= 2, "expected listen and screen host-socket modules");
    const missing = [];
    for (const [channel, file] of surface) {
      const owner = declared.get(channel);
      if (!owner) {
        missing.push(`${file} posts to ${channel}, but no OmiShell type declares static let channel = "${channel}"`);
        continue;
      }
      if (!registered.has(channel)) {
        missing.push(
          `${file} posts to ${channel} (${owner}.channel), but main.swift never registers that name on userContentController`,
        );
      }
      const ownerFile = swift.find((fileInfo) => fileInfo.text.includes(`class ${owner}`) || fileInfo.text.includes(`struct ${owner}`));
      if (ownerFile) {
        assert.match(
          ownerFile.text,
          /\baction\b/,
          `${owner} must decode the host-socket action field; a method-only dispatcher is the other transport`,
        );
      }
    }
    assert.equal(missing.length, 0, missing.join("\n"));
  });

  test("every dedicated host-socket channel the shell registers is referenced by a production host-socket module", () => {
    const extra = [];
    for (const channel of registered.keys()) {
      if (GENERIC_SHELL_CHANNELS.has(channel)) continue;
      if (!surface.has(channel)) {
        extra.push(`shell registers ${channel} but no *host-socket.ts module names that CHANNEL`);
      }
    }
    assert.equal(extra.length, 0, extra.join("\n"));
  });
});
