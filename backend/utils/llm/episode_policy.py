"""Shared claim privacy policy for production episode notes and offline judging."""

EPISODE_PRIVACY_RULE = '''A claim is private if ANY supporting source is private OR its content is sensitive:
health; money, housing or personal finances; credentials, security details or infrastructure secrets;
legal matters; intimate or relationship details; third-party personal information. This includes paraphrases
and inferences. A standard/public source never makes sensitive content public. A person's public professional
name or role alone is not sensitive; their private contact or personal details are. Mark every such claim private.'''

EPISODE_RELEVANCE_RULE = '''Center the owner: title and overview describe what happened to or for them in this
capture window. Admit screen/background facts only with an evidence-supported connection: the same participants,
the active call/meeting surface, a speech reference, the owner's messages with participants, or demonstrable owner
activity during a solo capture. Mere co-occurrence or an app/window label is not a connection. Do not manufacture a
conversation about incidental screens. Do not title the evidence or its capture quality; explain coverage gaps in
the body. Preserve uncertainty about agency, timing, attendance and intent. Earlier context explains this episode,
it does not become a new event or commitment. Never invent a topic when the owner's activity is unestablished.'''

EPISODE_PROVENANCE_RULE = '''said supports only content actually spoken in this capture. A name read from a call
tile, roster or message is shown/written, even when linked to a speech cluster; it was not said unless speech
independently contains it. shown describes directly observed screen/device state; written describes source text.
Conclusions, causal explanations, identity links and statements about what a capture does NOT establish are inferred,
not said/shown/written. Cite the observations supporting an inference without converting it to direct testimony.'''
