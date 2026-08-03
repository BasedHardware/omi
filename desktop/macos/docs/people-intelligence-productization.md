# People Intelligence — end-to-end productization

Goal: **every user** gets a People tab that understands their relationships across every
channel, computed **on-device first** (PII never leaves the machine except where the user has
already consented to Omi's model, and then only minimized derived data — never raw messages).

This doc is the contract every layer is built against. Status is tracked here and moves with the code.

## Architecture (one direction of data flow)

```
Connectors (local readers)          On-device engine (Swift)                 Surfaces
------------------------------      ----------------------------------       -----------------
iMessage  chat.db          ─┐       identity resolution (phone/handle)  ┐     People tab (list,
WhatsApp  ChatStorage      ─┤  ─►   who-knows-whom edges (group-size    ├─►   person detail,
Telegram  session          ─┤       normalized) + circles              │     connections, circles,
X         OAuth (backend)  ─┤       communities + category             │     communities, orgs)
LinkedIn  CSV              ─┤       affiliations (group/LinkedIn/email) │
Voice     conversations    ─┘       co-mentions (message text)         ┘     Chat ("tell me about X")
                                             │
                                             ▼  minimized per-person summary (opt-in)
                                    Model-backed narrative layer (Omi model)
                                    relationship type + "what's happened between us"
```

Every connector writes a local per-user export under `~/Library/Application Support/Omi/users/<uid>/`.
`PeopleGraphBuilder` consumes those, writes `people_social.json` / `people_communities.json` and
merges into `people_intelligence.json`, which the People tab reads. **Re-runs on every new-data event**
(app active, connector import, new conversation), throttled.

## Layer status

| Layer | Deterministic? | Status | Where |
|---|---|---|---|
| Cross-channel identity resolution | yes | **shipped (iMessage)** | `PeopleGraphBuilder` |
| Who-knows-whom edges (group co-membership) | yes | **shipped (iMessage)** | `PeopleGraphBuilder` |
| Circles | yes | **shipped** | `PeopleGraphBuilder` |
| Communities + category | yes | **shipped (iMessage)** | `PeopleGraphBuilder` |
| Continuous re-sync on new data | yes | **in this PR** | `PeopleGraphBuilder.syncIfNeeded` |
| WhatsApp group co-membership | yes | **next (Phase 2)** | Swift `WhatsAppReader` → engine |
| Affiliations (orgs) from group names + email | yes | **shipped** | `PeopleIntelDerivation.affiliations` |
| Relationship label (reach tier + group category) | yes | **shipped** | `PeopleIntelDerivation.relationshipLabels` |
| Group-chat meanings (`community_meanings`) | yes | **shipped** | `PeopleIntelDerivation.communityMeanings` |
| Edge derivation (`connections[].how`) | yes | **shipped** | `PeopleIntelDerivation.connectionHow` |
| `history_grounded` (thread really ingested) | yes | **shipped** | `PeopleThreadIngest.ingestedPersonKeys` |
| Affiliations from LinkedIn | yes | **next (Phase 2)** | LinkedIn CSV → engine |
| Co-mentions from message text | yes | **next (Phase 2)** | reader dumps bounded text → engine |
| Relationship type inference (`connections[].type`) | no (model) | **Phase 3** | model-backed layer |
| "What's happened between us" narrative | no (model) | **Phase 3** | model-backed layer |
| Telegram / full LinkedIn / X content into the graph | yes | **Phase 4** | per-connector readers |

Deterministic layers (Phase 2) are pure Swift ports of the reference pipeline in
`~/omi-people-intel-demo/engine/` (`build_edges.py`, `build_communities.py`, affiliation agent) and
carry no model dependency — they ship to every user as soon as ported and unit-tested.

**Conservatism rule for the deterministic layers.** A Phase-2 field is emitted only when the signal
behind it is real; where it is not, the key is left **absent** so the profile shows its honest
empty state instead of a plausible guess. In practice that means: an organization needs two
independent signals (an email domain plus a matching chat name, or the same name across two chats)
— a lone work-ish chat name produces nothing; the categorizer's `social` fallback bucket gets no
`community_meanings` gloss, because that bucket means "we could not tell"; and a relationship label
is a rank plus a category ("close · work"), never a sentence. Phase-3 keys (`who`, `now`,
`overall`, `facts`, `activities`, `openThreads`, `role`, `connections[].type`, `network_insights`)
are never written by the deterministic layers at all.

## Model-backed layer (Phase 3) — privacy contract

Relationship typing and the per-person "what's happened between us" narrative need a model.
Constraints:

1. **On-device data prep is mandatory.** The engine extracts a *bounded, minimized* per-person
   summary locally (channel counts, shared groups/orgs, a small window of recent message text with
   phone numbers/emails/addresses/codes redacted). Raw full history is never shipped.
2. **Same consent surface as voice.** Omi already processes the user's conversations with its model;
   this layer reuses that consent and pipeline. It is **off** until the user has enabled the People
   connectors, and it only ever sees the minimized summary from (1).
3. **Prefer on-device.** When an on-device model is available it is used with no network at all.
4. **Result is cached locally** in `people_intelligence.json` (`role`, `who`, `overall`, `now`,
   `facts`, `connections[].type`/`how`) and refreshed on the same throttled re-sync.

## Definition of done for each layer

A layer is "productized" only when: it runs in the shipping app for a fresh user with no manual
steps beyond the connector opt-in; it re-runs on the continuous-sync triggers; it has a unit test on
its pure core; and it degrades cleanly (no crash, no partial-state) when a source is missing.
