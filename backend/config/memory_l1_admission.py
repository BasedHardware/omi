"""L1 memory-extraction admission: do not pay for a row that cannot yield a memory.

Two deterministic verdicts, both already computed by the server without a model:

- ``noise``: the row is noise on Home. A server minimum, a media/noise content
  kind, or a row the relevance rules already settled as content-free. Nothing in
  it is worth a memory.
- ``short_owner_speech``: the owner spoke fewer than ``L1_MIN_OWNER_WORDS``
  words. "Thank you." yields no memory.

Unknown owner attribution is never evidence of owner absence: a row whose owner
cannot be identified still extracts.

Kill switch: ``EPISODE_COMPOSER_REUSE`` (default on). An explicit false
word restores one L1 call per processed conversation.
"""

from __future__ import annotations

from config.refactor_modes import default_on

COMPOSER_REUSE_ENV = 'EPISODE_COMPOSER_REUSE'

# Owner words below this cannot carry a durable fact. 30 sits above the 12-word
# notes floor (``NOTES_MIN_WORDS`` / ``WORD_FLOOR``), so a row that reaches L1
# already has notes, and well below the 100-word keep shortcut
# (``KEEP_WORD_COUNT``) where the model is never asked. At a normal speaking
# rate 30 words is 12-15 seconds: the shortest span that can state a fact about
# the owner rather than an acknowledgement.
L1_MIN_OWNER_WORDS = 30


def noise_skip_enabled() -> bool:
    """Kill switch: skip L1 for noise rows and short owner speech. On unless explicitly false."""
    return default_on(COMPOSER_REUSE_ENV)
