# The Even Realities "Add Agent" contract

Even publishes no specification for the custom-agent endpoint. This is the
contract **as observed from a real G2 + phone**, captured by the bridge itself
(`bridge/add-agent-capture.log`), not inferred from documentation or blog posts.

Captured 2026-07-27 against Even Realities app on iOS, G2 glasses.

## The request

```http
POST / HTTP/1.1
Authorization: Bearer <the token you typed into Add Agent>
Content-Type: application/json
User-Agent: Dart/3.11 (dart:io)

{"model":"openclaw","messages":[{"role":"user","content":"What should I focus on today?"}]}
```

| Detail | Observed value |
|---|---|
| Method / path | `POST` to the **root** of the registered URL — not `/v1/chat/completions` |
| Client | The **phone's** public IP, not the glasses. The phone does the HTTP. |
| User-Agent | `Dart/3.11 (dart:io)` — the Even app is Flutter |
| `model` | Always the literal **`"openclaw"`**, regardless of the agent name you chose |
| `messages` | A single `{"role":"user","content":"<transcript>"}`. **No conversation history** — every turn is stateless, so the agent cannot see what was asked before. |
| Speech-to-text | Done **on-device**; the endpoint receives finished text |

The `model` value is a fixed string, so don't key behavior off it. The bridge
accepts any value and echoes it back.

## The response

A standard OpenAI chat-completion body is accepted and rendered:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1785135941,
  "model": "omi",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

Confirmed working end to end: spoken question → glasses display, ~10s round trip
including Omi's agentic retrieval.

## Even AI intercepts some phrasings before your agent sees them

**This is the single most surprising behavior.** Even AI classifies the utterance
first, and only forwards it to the custom agent if it doesn't match a built-in
intent. Observed live:

| Said | Reached the agent? |
|---|---|
| "What should I focus on today?" | yes |
| "What did I have for dinner when I first met David?" | yes |
| "What was I doing on 4 July?" | yes |
| "What apart from work did I do on Fourth of July?" | yes |
| "what I need to get done today" | **no** — routed to Quicknote instead |

Questions reach the agent. Utterances that read as notes, reminders, or commands
get captured by Even's own note-taking feature, and nothing arrives at the
endpoint. There is no observed way to disable this from the agent side; the
workaround is phrasing — lead with an interrogative.

Because the interception happens on the phone, **an empty capture log is the
diagnostic**: if a query didn't arrive, Even routed it internally rather than the
bridge failing.

## What is still unknown

- **The client timeout.** Not measured. Answers taking ~10s are fine; the bridge
  caps its own wait at `OMI_EVEN_DEADLINE` (default 20s) and returns whatever
  partial answer exists rather than risking a silent client-side timeout.
- **Whether streaming responses are accepted.** Only non-streaming JSON has been
  tested, and it works.
- **The display limit in this mode.** Answers are fitted to ~380 characters, which
  renders correctly; the true cap has not been probed.
- **Whether `messages` ever carries history** in a multi-turn exchange. Every
  captured request had exactly one message.

## Re-capturing

The bridge logs every incoming agent request to `bridge/add-agent-capture.log`
with the bearer token redacted. If Even changes the contract, the diff shows up
there rather than as a mystery failure.
