# PAPER — package map

Builds one day's edition: five sections, each fed by a live source. Product spec
and rationale live in `docs/product/paper/SPEC.md`; this file is the code map.

## The shape

```
routers/paper.py          GET /v1/paper/{date}[/render], rate limited per UID
  └── edition.build_edition(uid, date, tier)          async assembler
        ├── context.gather                            the reader's own day
        ├── interests.get_profile                     what they care about
        ├── sources/*                                 the outside world
        ├── editorial.*                               the four model calls
        ├── photo.make_photo                          one drawn moment
        └── render.render_html / render_text          the page
```

## Modules

| Module | Owns |
|---|---|
| `context.py` | One day of the reader's record: conversations, screen activity, the stored summary, open action items. Also the day timeline and per-app focus time. Calls no model. |
| `interests.py` | The learned ranking rubric, derived from a fortnight of record and cached for a day. Every interest carries evidence or is dropped. |
| `editorial.py` | The only place a model writes prose: yesterday's story, newsletter clustering, external ranking, buzz selection, the cover line. |
| `photo.py` | One illustration of a real moment, via the LLM gateway's image surface. |
| `edition.py` | Assembles the sections, owns concurrency and per-source health. |
| `render.py` | Print-first HTML, 42-column plaintext for a thermal printer, and the hand-built day-strip SVG. |
| `sources/gmail_source.py` | Bulk mail, minus everything on the exclusion list. |
| `sources/calendar_source.py` | Today's events. |
| `sources/arxiv.py` | Recent submissions for the reader's interests. |
| `sources/hackernews.py` | What the internet is talking about. No model work. |
| `sources/discovery.py` | Fans interests out across the external sources. |

Models are in `models/paper.py`; the template is `templates/paper.html`.

## The four rules this package is built around

**No source, no print.** Anything asserted about the outside world names where it
came from, and that is enforced in the types rather than asked for in a prompt:
`Claim.is_printable`, `NewsletterStory.is_printable`, `Photo.is_printable`. A
newsletter story may only credit publications that actually sent mail, so
neither the model nor an injected message can invent a byline.

**A dead source costs one section, never the edition.** Every source returns its
own `SourceHealth`, `asyncio.gather` runs with `return_exceptions=True`, and the
page prints the full source roster. This exists because silent degradation is the
real failure mode: a paper that has quietly had no Gmail for a fortnight looks
exactly like a paper about a quiet fortnight. The corollary is that "nothing
found" and "the read failed" must never render the same — a failed calendar says
so rather than printing "Nothing scheduled".

**Rules before the model, where the danger is.** `gmail_source.exclusion_reason`
runs before any message reaches a prompt, and it scans every field the model will
be shown, not just the body. A regex that drops a real newsletter costs one
bullet; a model that decides a verification code is newsworthy costs an account.

**Measured, or not printed.** Focus time comes from real gaps between screen
samples, capped so an overnight gap cannot read as ten hours. A conversation
longer than four hours is a capture that never closed, so it keeps its place on
the timeline but its length is not counted. Charts are hand-built SVG from stored
values, never generated.

## Where things go wrong

- Screen rows are filtered by **string** comparison on an ISO timestamp, so day
  bounds use date prefixes (`context.screen_day_window`). Passing datetimes makes
  a single-day query return nothing at all.
- arXiv wants three seconds between queries. Firing them back to back returns
  200s with empty feeds, which is not a quiet week.
- Model-backed steps belong on `llm_executor`, not `db_executor`.
