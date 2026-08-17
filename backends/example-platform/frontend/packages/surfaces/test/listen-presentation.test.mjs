import assert from "node:assert/strict";
import test from "node:test";

import {
  isScriptedListenTranscript,
  SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED,
  SCRIPTED_LISTEN_TRANSCRIPT_TEXTS,
  SCRIPTED_LISTEN_TRANSCRIPT_TIMING,
} from "../src/production/listen-presentation.ts";

test("only the canned scripted STT pair is treated as not-the-user's-speech", () => {
  assert.equal(isScriptedListenTranscript([]), false);
  assert.equal(
    isScriptedListenTranscript([{ text: SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED }]),
    true,
  );
  assert.equal(
    isScriptedListenTranscript([
      { text: SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED },
      { text: SCRIPTED_LISTEN_TRANSCRIPT_TIMING },
    ]),
    true,
  );
  assert.equal(
    isScriptedListenTranscript([{ text: "harborline table at noon" }]),
    false,
  );
  assert.equal(
    isScriptedListenTranscript([
      { text: SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED },
      { text: "harborline table at noon" },
    ]),
    false,
  );
  assert.deepEqual(
    [...SCRIPTED_LISTEN_TRANSCRIPT_TEXTS],
    [SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED, SCRIPTED_LISTEN_TRANSCRIPT_TIMING],
  );
  // red-proof: treating any non-empty transcript as scripted hides real speech.
});
