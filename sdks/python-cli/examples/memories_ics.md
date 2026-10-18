# Put memories on a calendar timeline (.ics)

Use this recipe to see *when* memories were captured — each memory's
`created_at` becomes a 15-minute calendar event importable into Google
Calendar, Apple Calendar, and Outlook. It reads saved JSON exports, makes
no network requests, uses only the Python standard library. You need
Python 3.9+ and an authenticated `omi-cli` for the initial export.

Export your memories:

```sh
omi --json memory list > memories.json
```

## The converter

The script lives at [`memories_to_ics.py`](memories_to_ics.py) in this
directory — stdlib-only, RFC 5545 compliant.

Each VEVENT:

```
BEGIN:VEVENT
UID:omi-memory-m1@omi-cli
DTSTAMP:<now>Z
DTSTART:<created_at>Z
DTEND:<created_at + 15min>Z
SUMMARY:Loves espresso\, hates meetings
DESCRIPTION:Omi memory m1\nCategory: personal\nVisibility: public
STATUS:CONFIRMED
CATEGORIES:Omi
END:VEVENT
```

* **`SUMMARY`** carries the memory's content (RFC §3.3.11-escaped).
* **`DESCRIPTION`** lists id / category / visibility.
* **RFC 5545 §3.1 folding** at 75 octets, never splitting a UTF-8 character.
* Multi-file dedupe: each memory ID produces one event even across pages.

## Usage

```sh
python memories_to_ics.py memories.json -o memories.ics
```

Then import `memories.ics` into Google Calendar → Settings → Import, or
double-click it for Apple Calendar / Outlook.

## Safety

* `..` in the `-o` path is refused.
* Exclusive `xb` create — never overwrites; a failed write leaves no partial
  file.
* A memory with no `created_at` is skipped (it has no timeline anchor).
* Malformed JSON or a missing input exits `2`.
