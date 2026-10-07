# The on-device brain

How the local agent is put together, what has been measured, and what a small
language model would add — without pretending the numbers are better than they
are.

Reference device for every measurement below: **Samsung SM-A145F**, Exynos 3830
(2×A55 + 4×A55), 3.6 GB RAM, Android 15. A deliberately budget device: if it
works here, it works on the hardware people actually have.

---

## 1. What is already built and measured

| | Measured |
|---|---|
| MiniLM-L6-v2 routing accuracy | **67%** held-out (45 cases) |
| — median latency | **594 ms** |
| — peak RSS | **285 MB** |
| FunctionGemma 270M routing accuracy | **22%** |
| — refusal rate | **72%** |
| — median latency | **3,120 ms** |
| — peak RSS | **983 MB** |
| Model load, first run | **19,509 ms** |

Routing margins are **bit-identical across runs** — deterministic.

**The embedder beats the language model at routing, by 3×.** Not because the
model is bad, but because routing is a nearest-neighbour problem and
function-calling is a generation problem. FunctionGemma 270M matches prompt
tokens against action vocabulary, so `"do i have meetings today"` shares almost
nothing with `"Lists the events on the user's calendar for today"` and it
refuses. The embedder does not have that failure mode.

This is the single most important measured fact in this document. It is why the
architecture below keeps the router and does **not** replace it with an LLM.

---

## 2. The shape of the brain

```
              ┌─────────────────────────────────────────┐
utterance ──► │ ROUTER — MiniLM-L6-v2, 594 ms, 285 MB  │
              │  create_task │ create_reminder │ chat    │
              │  + out-of-domain abstain                  │
              └───────────────┬─────────────────────────┘
                              │
        create_task / reminder│              │ chat
                              ▼              ▼
                 regex slot extraction   ┌────────────────────────┐
                 (already excellent)     │ TOOL DISPATCH          │
                                         │  offline: date, GPS,   │
                                         │    local search,       │
                                         │    reminders, timers   │
                                         │  online:  weather,     │
                                         │    web search          │
                                         └───────────┬────────────┘
                                                     ▼
                                            ┌────────────────┐
                                            │ small LLM      │
                                            │ (optional)     │
                                            │ composes the   │
                                            │ reply from      │
                                            │ tool results   │
                                            └────────────────┘
```

### Why the router stays separate

1. It is **3× more accurate** at its job (67% vs 22%).
2. It is **5× smaller** (285 MB vs 983 MB).
3. It is **5× faster** (594 ms vs 3,120 ms).
4. It **cannot confabulate.** A router returns a class. It never invents a task.
5. Its failure is legible: a thin margin means "declined", and we fall back.

Adding an LLM to the routing path would make every one of those worse.

### Why a small LLM is still worth having

An embedder cannot write a sentence. So it cannot answer "what time is it", cannot
compose two tool results, and cannot paraphrase. `localAssistant.ts` currently
answers by **retrieval only** — quoting what was recorded, or refusing. That is
honest but limited.

The LLM's job is narrow: **take tool results and compose a reply.** Not routing.
Not slot extraction. Not deciding what is true.

---

## 3. Candidate: Gemma 4 E2B on LiteRT-LM

Released 2026-04-02, Apache 2.0. LiteRT-LM v0.14+ added streaming tool calling
on Android; v0.15 added `AutoToolChat`.

| Property | Value |
|---|---|
| Total parameters | 2.3B effective (5.1B with embeddings) |
| Architecture | Per-Layer Embeddings (PLE) |
| Modalities | **Text, image, audio** |
| Context | 128K (32K used in practice) |
| Quantisation | mixed 2/4/8-bit Gemma scheme |
| File size | **2,583 MB** |
| Working memory (text-only) | as low as **0.8 GB** via mmap |
| Tool calling | yes, native |

Audio input means one model could theoretically do **STT + tool calling + chat**.
See the risk in §5 before believing that.

### Measured on the SM-A145F — it does not fit

Run twice via `GemmaBenchActivity`, tag `[GemmaBench]`:

| | Run 1 | Run 2 |
|---|---|---|
| Model file | 2,468 MB | 2,468 MB |
| **Engine load** | **70,590 ms** | **70,826 ms** |
| **Peak RSS at load** | **1,522 MB** | **1,721 MB** |
| Decode / TTFT | **not reached** | **not reached** |
| Tool-call accuracy | **not reached** | **not reached** |

The process was killed during the first generation turn, both times. `lmkd`
gives the reason:

```
Reclaim 'com.google.android.apps.messaging' ... reason: device is low on swap
(1187808kB < 2222976kB) and thrashing (301%)
```

70 seconds is already disqualifying on its own — a cold start you wait a minute
for is indistinguishable from a crash. The kill is the deeper problem: the model
loads, then the first token request pushes the device into swap thrashing and
Android reclaims the process.

**The LiteRT cache does not rescue this.** The second run was 236 ms slower, not
faster. That is expected in hindsight: `.litertlm` files are already compiled, so
there is no compilation to warm.

### What this rules out, and what it does not

Ruled out on this hardware: **Gemma 4 E2B via LiteRT-LM, CPU backend.**

Not ruled out, and still open:

- **A smaller model.** Tool selection does not need 2.3B effective parameters. A
  0.5B-class tool-use model at ~400 MB would fit alongside the 285 MB router, and
  the tool-call accuracy question is unanswered because it was never reached.
- **GPU backend.** Untested — this phone has no NPU and LiteRT-LM's GPU path is
  aimed at devices with it.
- **Android AI Core / Gemini Nano.** Not available on this device.

The honest summary is that the *first* candidate failed, and the failure was
memory and latency rather than capability. Nobody has yet measured whether the
model would have chosen the right tool, because the phone could not keep it alive
long enough to ask.

### FunctionGemma 270M — passes on speed, unmeasurable on accuracy

The 275 MB model was already on the device, so it went first. It clears every
performance threshold Gemma 4 E2B failed:

| | Value | Threshold | |
|---|---|---|---|
| Engine load | **10,208 ms** | < 5 s | **2x over** |
| Peak RSS at load | 956 MB | — | fits |
| Peak RSS after tool phase | 1,458 MB | < 2,800 MB | fits |
| TTFT (median) | **428 ms** | — | fine |
| Decode | **21.4 tok/s** | >= 8 | **passes** |
| Tool accuracy | **unmeasurable** | >= 80% | — |

21.4 tok/s on a 1.6 GHz Cortex-A53 pair matches the Pi 5's published 35 tok/s
closer than the Pi 4's 1.7, so the decode hardware is far less of a constraint
than the earlier extrapolation assumed. **The LLM tier's problem on this phone is
memory residency, not arithmetic.**

The accuracy number does not exist yet, and the reason is specific:

```
TOOL_SUMMARY correct=0 total=15 accuracy=0.0 no_output=0
```

`no_output=0` is the load-bearing part. The model answered every case — it just
never answered in the requested shape. Asked to reply with
`{"tool":"<name>","arguments":{}}`, it says:

> I am FunctionGemma, a model optimized for function calls. I can only assist with
> requests...

FunctionGemma is fine-tuned for a native function-calling format and refuses
prose-format tool calling outright. Scoring that 0/15 as "wrong tool" would be
measuring the harness, not the model.

Measuring it properly means implementing LiteRT-LM's `ToolSet`, whose only method
is name-mangled (`provideTools$third_party_odml_...`) in 0.16.0. That is a
deliberate cost: an internal API that can change without notice, in exchange for
the one number that decides whether the tier exists.

The earlier router benchmark put FunctionGemma at 22% accuracy with 72% refusals,
but under a different harness, so it is a prior rather than an answer.

### Vendor numbers on other hardware

For reference only — none of these are the SM-A145F:

| Device | Backend | Decode tok/s | CPU memory |
|---|---|---|---|
| S26 Ultra (flagship) | CPU | 46.9 | 1,733 MB |
| iPhone 17 Pro | CPU | 25.0 | 607 MB |
| Raspberry Pi 5 (A76) | CPU | 35.0 | 1,628 MB |
| Raspberry Pi 4 | CPU | 1.7 | — |

## 4. Memory budget — the real constraint

Total RAM: **3.6 GB**, of which roughly 2.8 GB is realistically available.

```
Gemma 4 E2B working set        ~1,600 MB   (vendor, Pi-class CPU)
MiniLM router (measured)         285 MB
Whisper tiny (est.)              ~200 MB
                              ───────────
concurrent total               ~2,085 MB   against ~2,800 MB
```

It *fits* — with about 700 MB of headroom, which on Android is not much once the
system, camera stack and the app's own JS heap are counted.

**Therefore the models must be mutually exclusive, not concurrent.** The brain
is a state machine that holds exactly one model at a time:

```
idle ──utterance──► router(285MB) ──chat?──► unload router
                                            └─► LLM(1.6GB) ──► tools ──► reply
                                                                     └─► unload
```

Sequential loading costs a few seconds per transition. The 19.5 s MiniLM load
already measured shows this is not hypothetical — that number is what motivated
the `warmUp()` call so the cost is paid while idle rather than inside a tap.

---

## 5. What genuinely cannot be offline

| Request | Offline? | Why |
|---|---|---|
| Transcription (Whisper / Gemma audio encoder) | **yes** | model on device |
| Speaker ID | **yes** | local embedding clustering |
| Tasks, reminders, timers | **yes** | local state |
| Conversation search | **yes** | on-device store |
| Date, time, alarms | **yes** | system clock |
| GPS coordinates | **yes** | hardware receiver |
| Reverse geocoding ("you are near the station") | **no** | needs a gazetteer |
| **Weather** | **no** | remote data by definition |
| **Web search** | **no** | network by definition |

"Weather and web search, fully offline" is not a hard problem, it is a
contradiction. A cached forecast can be *replayed* offline, but that is not
knowing the weather, and the difference matters when someone asks whether they
need a coat.

---

## 6. Tool registry

Tools declare whether they need the network, so the assistant can say why it
cannot answer rather than failing.

```ts
interface BrainTool {
  name: string;
  /** false → unavailable without a session or a connection. */
  needsNetwork: boolean;
  description: string;
  run: (args: Record<string, unknown>) => Promise<unknown>;
}
```

| Tool | Network | Notes |
|---|---|---|
| `get_current_time` | no | trivial, and the first thing a small LLM gets right |
| `get_location` | no | GPS fix; cached fix returned if stale |
| `search_conversations` | no | the local store; accepts `speaker` filter |
| `list_tasks` / `add_task` / `add_reminder` | no | already working |
| `set_timer` / `set_alarm` | no | via system intents |
| `get_weather` | **yes** | refuse offline with a stated reason |
| `web_search` | **yes** | refuse offline with a stated reason |

Two design rules learned the hard way:

1. **One model at a time.** Concurrent models evict each other.
2. **Never let the LLM see a question it cannot answer offline** without the tool
   registry saying so first. Otherwise it confabulates, and the 270M's 72%
   refusal rate is the good outcome.

---

## 7. Staging plan

Each step is gated on a measurement, not an assumption.

### Step 1 — benchmark Gemma 4 E2B — **done, it failed**

Measured twice on the SM-A145F: 70 s load, 1.5-1.7 GB RSS, killed during the
first generation turn by swap thrashing. See §3.

### Step 2 — benchmark a 0.5B-class tool-use model

The unanswered question, and now the only one worth asking. Tool selection needs
far less than 2.3B effective parameters, and the accuracy number is unknown
because the 2B model could not stay alive long enough to be asked.

Constraint: the model must coexist with the 285 MB router and ~200 MB of Whisper
inside ~2,800 MB, so **~1.5 GB is the ceiling for the whole tier** and a
~400 MB model is the comfortable target.

Decision rule, unchanged:

- **≥ 8 tok/s and tool accuracy ≥ 80%** → proceed to composition
- **2–8 tok/s** → restrict it to composing short tool replies
- **< 2 tok/s, or tool accuracy < 60%** → keep retrieval-only as the ceiling

Add a hard gate before anything else: **if load exceeds 5 seconds, stop.** A
model that takes 70 seconds to become usable cannot be behind a button, whatever
it scores.

### Step 2 — tool selection only

The LLM's *first* job should be picking a tool and filling its arguments —
output is a JSON blob, not prose. That is a much easier task than generation,
needs a shorter context, and is measurable without prose quality judgements.

### Step 3 — reply composition

Only then let it write a sentence from tool results. Cap the length hard.

### Step 4 — multi-step, with gates

"Pay the electricity bill" is a chain: find the bill → check balance → confirm →
pay → produce a receipt. Model the chain as **explicit steps with a confirmation
gate before anything irreversible**, not as free-form agent planning.

Payment itself is out of reach for a third-party app: Android does not reliably
permit driving another app's UI. It needs a real payments API or a deep link from
the bank's app.

---

## 8. What would change the plan

| Change | Effect |
|---|---|
| Android AI Core / Gemini Nano available | Replaces the whole LLM tier. Requires a supported device — the SM-A145F is almost certainly not one. |
| Device with 6 GB+ RAM | Concurrent models become possible; drops the load-switch penalty |
| A better 0.5B tool-use model | The most likely real win — tool selection needs far less capability than prose |
| Server available (signed in) | The assistant already prefers the server; local is the fallback, not the competitor |

---

## 9. Honest summary

- The **router is done and proven** on real hardware: 67%, 594 ms, 285 MB.
- **Retrieval-based chat is done** and refuses rather than inventing.
- A **small LLM would add reply composition and tool dispatch**, and nothing else.
- On this device it will be **slow** — the Pi 4 comparison suggests single-digit
  tok/s — and it is not yet measured here at all.
- **Weather and web search can never be offline**, regardless of model size.

The next useful action is a benchmark, not an implementation.