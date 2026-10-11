# Host collection of finalized-WAL recovery

**Experimental physical workflow.** The collector is covered by mocked device
tests; the complete real-device sequence has not passed. See
[status and measured layers](IPHONE_HARNESS.md) before using its receipts.

`physical_capture_collect.py` operates an already installed, separately named
qualification app. The default is an offline plan. `--execute` performs the
exact bundle's termination/relaunch and writes upload approval only after copied
recovery bytes match. It does not install apps or restart services.

```sh
python3 scripts/dev-harness/physical_capture_collect.py \
  --device "$CAPTURE_DEVICE" \
  --bundle-id "$CAPTURE_BUNDLE" \
  --artifact "$CAPTURE_ARTIFACT_ZIP" \
  --build-receipt "$CAPTURE_BUILD_RECEIPT" \
  --server-receipts "$CAPTURE_STATE/mic" \
  --output "$CAPTURE_EVIDENCE" \
  --timeout 900
```

Review the printed plan; add `--execute` for the authorized device run. The device
must be an explicit UDID/UUID, the bundle must contain `.capture-qualification.`,
and output must be a new directory outside Git. The ZIP must contain exactly the
signed app files recorded by `physical_capture_build.py`; package it with one
`.app` root (optionally under `Payload/`). Symlink entries are refused. Do not
rebuild or replace the artifact/receipt during collection.

The collector waits for `awaiting_termination`, copies only the selected app's
state, WAL index, and selected audio snapshots, and checks their hashes/statuses.
It queries the exact installed bundle, matches the event PID against the complete
installed executable URL, sends SIGKILL, and independently queries until that PID
has exited. It then relaunches the same bundle, verifies a different app boot
nonce and matching executable, and copies/checks the recovered bytes. Only then
can it exclusively create the current run's upload approval file.

After upload/reconciliation it copies the remaining snapshots, joins completed
server receipts by per-file job ID, emits `manifest.json` and `lifecycle.json`, and
runs `physical_capture_verify.py`. The output also includes timed devicectl JSON
operation receipts and hashes. Polling and individual commands have finite
limits. A failed/refused operation leaves its collected evidence for inspection;
it does not automatically retry a kill or clean state.

`build-identity.json` hashes the entire recorded build receipt, including Dart,
native, defines, and signed-file hashes. The manifest uses that same digest in
`dirty_input_sha256` (a recorded-build identity, not just a Git diff digest).
The artifact ZIP is independently checked against the pinned signed-file map.

The collector cannot read/hash the installed executable independently. Matching
bundle/version/container URL proves process ownership, **not** that its bytes
match the supplied ZIP. The lifecycle records
`installed_binary_hash_independently_verified:false`; preserve the parent's
installation receipt tying its actual install to the signed app tree alongside
these results before attributing device behavior to a source build. The offline
oracle always reports `hardware_qualified:false`. These results do not certify
transcription, audio quality, or an unflushed mid-write capture tail.

Hermetic tests (mocked device only):

```sh
python3 scripts/dev-harness/physical_capture_collect_test.py -v
```
