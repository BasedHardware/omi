# `context_core` — the portable half of the data plane

A dependency-free C++17 library holding the **pure decision rules** that turn stored rows into an
answer, plus a flat C ABI so both hosts can call it: the macOS Swift package links it into
`ContextCore`, and the Windows CMake project (`../windows`) builds the identical sources.

It contains no I/O, no SQLite, no platform API, and no text tokenization. That is the whole point of
where the seam was cut.

## Why these three pieces, and nothing else

The app is macOS-only and stays that way — capture is ScreenCaptureKit, CoreAudio taps and Vision
OCR, none of which have a Windows equivalent worth pretending about. What *is* portable is the
layer underneath: the rules that decide when a conversation ended, which of a hundred matching rows
a reader should actually see, and how many separate things a run of screenshots represents. Those
rules are calibrated against real captured data (the constants below carry their measurements), and
a second implementation of them would be a second set of answers to the same question.

So the seam is drawn at **everything that is arithmetic over already-extracted facts**:

| Extracted | Why it is portable | Why it is worth extracting |
|---|---|---|
| `ctx_should_open_new_session` | one subtraction and one comparison | it is the entire session model; a host that gets it wrong shatters or merges conversations |
| `ctx_recall_score` / `ctx_relevance_floor` | the blend of two normalised signals and a decay | the weights are calibrated against a real ranking defect; a divergent copy silently re-introduces it |
| `ctx_moment_groups` | set arithmetic over opaque hashes and opaque keys | the churn-relative novelty bar is the subtlest rule in the product and the most expensive to re-derive |

What deliberately stays in Swift is everything that needs **Unicode**: tokenizing a query into FTS
terms, folding a window title to its words, hashing OCR into a word set. `CharacterSet.alphanumerics`
is a full Unicode property, and reimplementing it in C++ without ICU would be a correctness
regression wearing a portability badge. So the caller hands this library keys it has already
normalised and word hashes it has already computed; the library never looks inside either.

The ABI is therefore free of Unicode, of allocation, and of string ownership: keys arrive as opaque
byte ranges compared for equality only, words arrive as opaque 64-bit values compared for set
membership only, and every buffer is owned by the caller.

## Building and testing

Standalone, on macOS or Windows:

```bash
cmake -S desktop/context-for-claude/core -B /tmp/context-core-build
cmake --build /tmp/context-core-build
ctest --test-dir /tmp/context-core-build --output-on-failure
```

The tests are a single translation unit with a hand-rolled assertion macro — no GoogleTest, no
FetchContent, nothing to resolve. A test dependency that has to be downloaded is a test suite that
stops running the first time a machine is offline, and this library exists precisely to be built on
machines nobody has configured yet.

On macOS the same sources are also compiled by SwiftPM as the `ContextCoreCxx` target and covered a
second time, through `ContextCore`, by `swift test --package-path desktop/context-for-claude`. The
two builds must agree; if they ever do not, the CMake build is the one that is honest, because it is
the one Windows uses.
