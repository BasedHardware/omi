import assert from "node:assert/strict";
import test from "node:test";

import { accountPresentation } from "../src/production/settings-presentation.ts";

const signedIn = {
  identity: { displayName: "Alex Rivera", email: "alex@example.com" },
  appearance: "system",
  entitlement: null,
};

const signedOut = { identity: null, appearance: "system", entitlement: null };

test("account presentation keeps a cached identity on screen during initial-loading", () => {
  assert.equal(accountPresentation("initial-loading", null), "loading");
  assert.equal(accountPresentation("initial-loading", signedOut), "loading");
  assert.equal(accountPresentation("initial-loading", signedIn), "signed-in");
  assert.equal(accountPresentation("refreshing", signedIn), "signed-in");
  assert.equal(accountPresentation("ready", null), "loading");
  assert.equal(accountPresentation("ready", signedOut), "signed-out");
  assert.equal(accountPresentation("ready", signedIn), "signed-in");
  assert.equal(accountPresentation("unavailable", null), "unavailable");
  assert.equal(accountPresentation("unavailable", signedOut), "unavailable");
  assert.equal(accountPresentation("unavailable", signedIn), "signed-in");
  // red-proof: prefer phase === "initial-loading" over snapshot.identity so a
  // cached signed-in account disappears behind common.loading.
});
