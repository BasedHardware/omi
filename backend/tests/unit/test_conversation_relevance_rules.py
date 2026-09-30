"""Deterministic relevance rules (utils/conversations/relevance_rules.py).

Every utterance below is invented; none is copied from a real transcript. The
patterns mirror what the rules measured against on real capture: backchannels,
function-word-only fragments, microphone checks, repeated phrases,
multilingual fillers, and the short utterances that must never be discarded.
Each case is (texts, speech_seconds, expected) where expected is 'keep',
'discard', or None (the model decides).
"""

from typing import List, Optional, Sequence, Tuple

import pytest

from utils.conversations.relevance_rules import deterministic_relevance

Case = Tuple[Sequence[str], Optional[float], Optional[str]]

_LONG = (
    'We walked through the quarterly roadmap and agreed that the onboarding flow needs a rewrite before '
    'the spring launch. Priya will draft the new copy, Tom owns the analytics events, and we will review '
    'both on Tuesday. The main open question is whether the free tier keeps offline sync, which depends '
    'on the storage cost estimate that finance promised by the end of the week. We also discussed hiring '
    'a second designer, moving the weekly sync to Thursdays, and trimming the settings screen so that new '
    'users see only the three options they actually need on day one. '
    'Finally, everyone agreed to send written feedback on the pricing page before the Friday demo.'
)

CASES: List[Case] = [
    # --- must never be discarded: short but meaningful ---------------------
    (['Call mom before five.'], 1.4, None),
    (['Yes.'], 0.3, None),  # an answer, not filler
    (['No.'], 0.3, None),
    (['Buy milk.'], 0.8, None),
    (['Remind me to email Sarah tomorrow.'], 2.1, 'keep'),
    (["Don't forget to feed the cat."], 1.9, 'keep'),
    (['Sarah.'], 0.4, None),
    (['May.'], 0.3, None),
    (['Will?'], 0.3, None),
    (['Dentist at 3:30 on Thursday.'], 1.6, None),
    (['The door code is 4 7 1 9.'], 2.2, None),
    (['Pick up the dry cleaning.'], 1.5, None),
    (['I need the blue folder.'], 1.2, None),
    (['Yes, it is in the top drawer.'], 1.3, None),
    (['Is Maya coming tonight?'], 1.1, None),
    (['Twenty dollars.'], 0.9, None),
    (['Okay, see you at noon.'], 1.2, None),
    (['I do have time for that, but', 'Jordan said no.'], 2.4, None),
    (['明天下午三点开会。'], 1.8, None),
    (['Да, конечно.'], 0.9, None),
    (['Anh gửi em cái hợp đồng nhé.'], 1.7, None),
    (['Okay.', 'Testing one two three, remind me to buy stamps.'], 3.0, 'keep'),
    (['Testing one two three, call mom.'], 2.0, None),
    # --- substantive: keep without a model call -----------------------------
    ([_LONG], 60.0, 'keep'),
    # --- pure backchannel / interjection -----------------------------------
    (['Mm-hmm.'], 0.3, 'discard'),
    (['Uh-huh, uh.'], 0.8, 'discard'),
    (['Oh'], 0.3, 'discard'),
    (['Yeah, yeah.', 'Okay.'], 1.0, 'discard'),
    (['Uh', 'Yeah.'], 0.3, 'discard'),
    (['Hmmmm.'], 0.9, 'discard'),
    (['Ha ha ha.'], 0.4, 'discard'),
    (['Thank you, thank you. Alright.'], 1.5, 'discard'),
    (['Hi.', 'Hello.', 'Bye-bye.'], 1.2, 'discard'),
    (['Yeah. Yeah. Yeah.'], 900.0, 'discard'),  # absurd span from a sync segment
    (['嗯嗯。'], 0.5, 'discard'),
    (['好的，对对对。'], 0.9, 'discard'),
    (['Ừ.'], 0.2, 'discard'),
    (['Ага.'], 0.3, 'discard'),
    # --- function words only (no retrievable content) ----------------------
    (['What is your'], 0.6, 'discard'),
    (['Why are you not?', 'Why not?'], 1.1, 'discard'),
    (["That's all."], 0.4, 'discard'),
    (["I don't know, I think so."], 1.2, 'discard'),
    (['So I just, like, you know.'], 1.0, 'discard'),
    (["Yeah, I'm not sure about that one."], 1.3, 'discard'),
    (['If you want to do it, then we could.'], 1.8, 'discard'),
    (['', '   '], 0.0, 'discard'),
    # --- microphone checks ---------------------------------------------------
    (['Testing, one, two, three. Can you hear me?'], 3.2, 'discard'),
    (['Mic test, 1, 2, 3, hello hello.'], 2.5, 'discard'),
    # --- repeated phrases: a looping transcriber and pronunciation practice look
    # alike, so repetition alone never discards --------------------------------
    (['I have a cup.'] * 4 + ['I have a.'] * 4 + ['Thank you.'], 40.0, None),
    (['A narrated explanation of this chapter.'] * 70, 665.0, 'keep'),  # kept by length
    # --- ambiguous: carries content words, the LLM decides -------------------
    (['Coming over there in a second.'], 1.3, None),
    (['Got a new mat for you. Come on.'], 1.6, None),
    (['One inch of rain today. Next we'], 2.0, None),
    (['Wash the car.'], 0.9, None),
    (['The next stop is Pine Street.'], 2.0, None),
    (['Alexa, volume four.'], 1.1, None),
    (['Could you check the logs for me?'], 1.9, None),
]


@pytest.mark.parametrize('texts,speech_seconds,expected', CASES)
def test_verdict(texts, speech_seconds, expected):
    verdict, rule = deterministic_relevance(texts, speech_seconds)

    assert verdict == expected, rule
    assert rule and rule.replace('_', '').isalpha()


def test_duration_never_decides():
    for seconds in (None, 0.1, 5.0, 3600.0):
        assert deterministic_relevance(['Call mom before five.'], seconds)[0] is None
        assert deterministic_relevance(['Mm-hmm.'], seconds)[0] == 'discard'
