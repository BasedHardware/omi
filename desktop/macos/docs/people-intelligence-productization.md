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

### Who becomes a person (`PeopleSelection`)

`buildCanonicalPeople` deliberately makes a node out of **every** identity in the exports — an edge
needs both endpoints. That is right for a graph and wrong for a directory: a measured cold start on
one machine produced **1,825 nodes**, 988 of them unbridged WhatsApp `@lid` tokens scraped out of
four broadcast lists (591 / 275 / 247 / 204 members) and 1,398 of them with no message ever
exchanged. `PeopleSelection.select(people:graph:communities:)` is the stage between the two. It is
pure — no IO, no Contacts, no clock — and partitions every candidate into `featured` or a `Drop`
carrying one stated reason.

The rule: **a person is someone you can address, and either someone you have actually talked with or
someone you can name who shares a real group with you.** Three bars, first failure wins:

| Bar | Fails as | Why |
|---|---|---|
| Addressable — a phone key or a real email | `unaddressable` | An opaque platform token can never be named or messaged. |
| Relationship evidence — messages, or a group of 2…`maxGroup` members | `broadcastListOnly` / `noSignal` | Row 412 of a 591-member list is not a relationship. The ceiling is the same `maxGroup` the edge builder uses. |
| Nameable, or a two-way exchange | `groupOnlyUnnamed` / `oneWayUnnamed` | An answered conversation is identity enough; a one-directional burst is a broadcaster, not a person. |

Naming is exhausted **before** anyone is dropped for being unnamed (`PeopleNaming`): address book →
the connector's own `contact_name` → a name this machine resolved on an earlier run
(`people_identity.json`) → the email local part. Only the first three are *asserted* and may claim
`contactName`; a name read off an address is a reading and is never persisted as durable.

`stats.featured` + `stats.dropped` always equal the candidate count, and `stats.dropped_reasons`
carries the breakdown, so the People tab can say how many contacts it is not showing and why. Both
the create path and the merge path write it; the merge path additionally may never write a dropped
node and may never remove a card a previous run featured.

### Person identity (`people_identity.json`)

A person is identified by their **identity keys** — `phone_last10` for phone-shaped handles, the
lowercased handle otherwise — never by their display name. `people_identity.json` maps each identity
key to the person id first assigned to it (`PersonIdentityLink`), and `buildCanonicalPeople` prefers
that stored id over a freshly-slugged name.

That is what makes a contact rename a display-name change and nothing more. Without it `slug(name)`
*is* the identity, so a rename silently minted a second person and detached that person's saved
`people_overrides.json` decisions, their `person:<id>` memory tags already on the server, and their
`people_photos/<id>.jpg`. `PeopleIdentityTests` guards it: the test renames a contact between two
pipeline runs and asserts all four survive.

Each person card therefore carries:

| Field | Meaning |
|---|---|
| `handles` | `{phones: [...], emails: [...]}` — the identity keys this person resolved by. Unioned on merge, never replaced. |
| `personUUID` | The backend `Person.id` this identity is bridged to. Fill-in only; never repointed at a second record. |

`PeopleIdentityBridge` resolves `personUUID` lazily and off the hot path: one `GET /v1/users/people`
plus a capped number of `POST /v1/users/people` (idempotent by name) per throttled run, stored
against the identity keys so the binding outlives a rename. `PeopleThreadIngest` then stamps that
uuid as `person_id` on the counterpart's segments only — which is what lets the backend's
`infer_subject_from_segments` attribute a 1:1 thread's memories to that person instead of `unknown`.

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
| "What's happened between us" narrative (`who`/`now`/`overall`/`facts`/`activities`/`openThreads`) | no (model) | **shipped** | `PeopleNarrative` → `POST /v1/people/dossiers` |
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

### How the narrative half satisfies that contract today

`PeopleNarrative` (desktop) + `POST /v1/people/dossiers` (backend) implement points 1, 2 and 4.
Point 3 has nothing to prefer yet: there is no on-device language model in this repository.

- **(1) Bounded, minimized, redacted — by reusing the one redactor.** The narrative request carries
  **only** backend person ids and evidence fingerprints; no message text, no names, no transcripts.
  What the model summarizes is memories Omi already extracted on the account, and the messaging
  half of those came through `PeopleThreadIngest.buildTranscript`, which redacts phone numbers,
  emails and OTP codes (`PeopleThreadIngest.redact`) and caps the window at the last 40 messages
  *before* anything leaves the machine. There is deliberately no second redactor.
- **(2) Same consent surface.** Gated on `peopleIMessageExport`, the same flag as the graph, the
  memory writer and the thread ingest.
- **(4) Cached locally, refreshed on the throttled re-sync.** Results are merged into
  `people_intelligence.json`; `people_narrative_ledger.json` stores the evidence fingerprint each
  card was generated from, so a person whose evidence has not changed is answered `unchanged` with
  no model call. Runs from the same app-became-active seam as `PeopleGraphBuilder.syncIfNeeded`,
  sequenced after it, on its own 6-hour throttle and capped at 12 people per run.

**Grounded or absent — enforced, not requested.** The backend prompt requires a citation for every
sentence and list item, and `utils/llm/people_dossier.ground_dossier` then *discards* anything whose
citation is missing, invented, or attached to a different field, plus anything hedged. A field the
model could not ground never reaches the card, so the profile keeps the same honest empty state the
deterministic layers produce. `openThreads` is held to the strictest bar: an evidence line must show
a specific request, promise, question or decision left unresolved.

**Correctable.** Each surviving claim ships with the evidence ids behind it (`narrative.claims` on
the card), and because the narrative writes `facts`, the existing `people_overrides.json` review
path corrects or drops a wrong one — and a later refresh does not reinstate it.

## Definition of done for each layer

A layer is "productized" only when: it runs in the shipping app for a fresh user with no manual
steps beyond the connector opt-in; it re-runs on the continuous-sync triggers; it has a unit test on
its pure core; and it degrades cleanly (no crash, no partial-state) when a source is missing.
