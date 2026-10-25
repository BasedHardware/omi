"""Open-loop prompt rules, appended to the notes instructions when enabled."""

OPEN_LOOP_EXTRACTION_RULES = '''OPEN LOOP EXTRACTION RULES (fields delegated_by_user, commitments_by_others, observed_issue_or_blocker)
These capture follow-ups the account owner may later be asked about ("did it happen?"). They never
duplicate, replace or absorb an action item: extract action_items first and exactly as you would
without these fields.
- delegated_by_user: the owner asked, assigned or instructed someone else (a person, teammate,
  contractor, or an AI/coding agent) to do something: "can you…", "please find…", "I asked them to
  look into X". Include it even if the other party's reply is not shown.
- commitments_by_others: another person (or team/vendor/agent) said they WILL do something for the
  owner or the owner's project: send, check, fix, book, deliver, introduce, find, report back.
- UNATTRIBUTED REQUESTS COUNT. Summaries often use the passive or "they"/"someone". When a concrete
  deliverable was requested or promised in the owner's work or errands but the source does not say
  who asked or who will do it, still record it: put it in delegated_by_user if the owner (or the
  owner's side) plausibly asked, otherwise in commitments_by_others, with who "unknown". Never
  invent a name.
- Only real, checkable deliverables. Skip small talk, offers about the immediate moment ("I'll pass
  the salt"), hypotheticals, jokes, things completed within the conversation itself, and requests
  between two other people that do not involve the owner's work or errands.
- who: the person/role as named in the source ("Maya", "the teammate", "the coding agent",
  "unknown"). what: a short verb phrase of the deliverable, at most 12 words ("send the vendor
  write-up"). by_when: only when the source states or clearly implies a time; an ISO 8601 date in
  the user's timezone or a quoted phrase ("Monday"); otherwise null. evidence: a quote or close
  paraphrase from the source, at most 20 words. work_related: true when it concerns the owner's
  job, product, codebase or company.
- observed_issue_or_blocker: at most ONE, otherwise null. Only these two narrow kinds:
  "work_defect": a concrete defect in the owner's own product/codebase/device was observed (a bug,
  a regression, a crash, a lag, wrong UI) and nobody said it was filed or fixed; what is the next
  step as an imperative ("File the login-screen crash bug").
  "errand_blocker": a dated or time-bound errand of the owner's is blocked on a missing piece of
  information or a missing resource that nobody has committed to getting (e.g. a notary is needed
  for Friday's filing and none is lined up).
  Not observations in general, not advice, not opinions, not anything already in action_items,
  open tasks, delegated_by_user or commitments_by_others.
- Never record relationship, medical or legal inferences, or details of another person's private life.
- Empty arrays and null are the expected answer for most conversations (fragments, entertainment,
  meals, chatter).'''
