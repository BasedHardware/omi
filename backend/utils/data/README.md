# Dream common English words

`common_english_words.txt` is a small, manually curated list of frequent English
words, plus everyday food and measurement terms. It is bundled, lowercase,
unranked, and requires no corpus download or new dependency. It deliberately
covers common vocabulary rather than claiming to be a complete dictionary or
an exact corpus top-N ranking. Extend it with ordinary dictionary words when
synthetic regression cases expose gaps; keep names and specialized jargon out.

Dream checks only an entire single English token proposed as `kind=jargon`,
after trimming and lowercasing. Person, organization and project terms, compound
terms, and aliases are unaffected. Words absent from this finite list remain
eligible; membership is a conservative admission rule, not a language detector.
