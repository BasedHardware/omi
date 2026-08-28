---
title: JIT ledger slot and playbook governance
description: Stable knowledge-ledger slots, profile ordering, and progressive-disclosure limits.
---

`knowledge_ledger.v1` uses an append-only slot registry implemented in
`backend/models/knowledge_ledger_policy.py`. Canonical slot names are released
wire values. A canonical name may gain spelling aliases, but it must not be
renamed or reused for a different meaning.

| Render order | Canonical slot | Accepted aliases |
| ---: | --- | --- |
| 10 | `preferred_name` | `name`, `display_name`, `called_name` |
| 20 | `pronouns` | `preferred_pronouns` |
| 30 | `primary_language` | `language`, `preferred_language` |
| 35 | `age_years` | `age` |
| 40 | `timezone` | `time_zone`, `user_timezone` |
| 50 | `home_city` | `city`, `home_location`, `residence_city` |
| 60 | `work_city` | `office_city`, `work_location` |
| 70 | `occupation` | `job`, `job_title`, `role` |
| 80 | `employer` | `company`, `workplace` |
| 90 | `communication_style` | `preferred_communication_style` |
| 100 | `dietary_preferences` | `diet`, `dietary_restrictions` |
| 110 | `current_focus` | `current_priority`, `primary_focus` |

New semantic writes fail closed on an unknown slotted name. Historical
migration preserves the fact as unslotted history instead of inventing a new
prompt field. Unslotted facts remain searchable but never enter the always-on
profile.

The renderer selects one row per canonical slot. Authority wins first:

1. direct user statement or explicit remember;
2. onboarding;
3. reusable in-agent conclusion;
4. daily reconciliation inference;
5. legacy migration.

Within the same authority, the newest valid fact wins, then curation weight,
then stable row identity. Curation is bounded to `-100...100` and cannot make
an inference outrank a direct user statement. Final lines use the registry
order, not discovery order or curation score. The full profile is capped at
2,400 characters and each normalized fact value at 360 characters.

Playbook descriptions and bodies are separate. Descriptions are normalized to
one line and capped at 360 characters; the prompt receives only an 800-character
index of current, review-visible handles. `read_playbook` is the
owner-scoped body hydration boundary. Bodies are capped at 24,000 characters,
new versions supersede prior rows transactionally, and normal projection and
vector outboxes synchronize searchable descriptions. Search never indexes or
returns the body through the compact handle endpoint. Only the recurring-
workflow write authority may create a playbook through the ledger helper.
