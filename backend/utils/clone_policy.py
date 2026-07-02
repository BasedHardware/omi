"""Safety-first send policy for the AI clone / on-behalf responder.

The clone drafts replies in the user's voice; this module decides whether a draft
may be sent automatically or must be held for human review. Defaults are
conservative: review-first, allowlisted contacts only, never auto-send sensitive
content, and respect quiet hours. All logic here is pure and deterministic so it
is fully unit-tested without the LLM or any I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Send modes.
REVIEW = "review"  # default: always draft, the user approves before sending
AUTO = "auto"  # opt-in: may auto-send when every guardrail passes

# Decisions.
ACTION_SEND = "send"  # safe to send now
ACTION_REVIEW = "review"  # queue a draft for the user to approve/edit
ACTION_HOLD = "hold"  # do not send now (e.g. quiet hours); revisit later

# Substrings that make a message "sensitive" and therefore never auto-sent.
_SENSITIVE_KEYWORDS = (
    # money / payments
    "venmo",
    "paypal",
    "zelle",
    "wire transfer",
    "bank account",
    "routing number",
    "credit card",
    "debit card",
    "invoice",
    "refund",
    "pay me",
    "send money",
    "gift card",
    "crypto",
    "bitcoin",
    "wallet address",
    # credentials / identity
    "password",
    "passcode",
    "one-time code",
    "verification code",
    " otp",
    " 2fa",
    "social security",
    " ssn",
    # legal / medical / emergency
    "lawyer",
    "attorney",
    "lawsuit",
    "contract",
    "sign here",
    " nda",
    "diagnosis",
    "prescription",
    "hospital",
    "emergency",
    " 911",
    "suicide",
    "self-harm",
    # high-stakes personal
    "break up",
    "get fired",
    "laid off",
    "divorce",
)


def is_sensitive_content(*texts: Optional[str]) -> bool:
    """True if any provided text looks sensitive or high-stakes (money, credentials,
    legal/medical/emergency, high-stakes personal). Case-insensitive substring match.
    A leading space is padded so tokens like "otp"/"ssn"/"911" match on word-ish
    boundaries and do not fire inside unrelated words.
    """
    haystack = " " + " \n ".join(str(t).lower() for t in texts if t) + " "
    if not haystack.strip():
        return False
    return any(keyword in haystack for keyword in _SENSITIVE_KEYWORDS)


# Patterns that indicate an incoming message is trying to hijack the clone (prompt
# injection). Nik's essay: "the bot checks for prompt injections... anything
# suspicious I review myself." The incoming message is untrusted; a hit forces review.
_INJECTION_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "ignore the above",
    "disregard previous",
    "disregard the above",
    "forget previous",
    "forget everything",
    "new instructions",
    "system prompt",
    "you are now",
    "pretend to be",
    "reveal your prompt",
    "reveal your instructions",
    "print your instructions",
    "repeat the text above",
    "developer mode",
    "jailbreak",
    "do anything now",
    "override your",
    "your real instructions",
    "as an ai",
)


def is_prompt_injection(*texts: Optional[str]) -> bool:
    """True if any text looks like a prompt-injection / hijack attempt. A hit forces
    human review and never auto-sends, no matter the other guardrails."""
    haystack = " ".join(str(t).lower() for t in texts if t)
    if not haystack.strip():
        return False
    # Collapse whitespace and punctuation between words so obfuscated variants
    # ("ignore\nprevious", "ignore-previous", "ignore...previous") still match a
    # spaced pattern like "ignore previous".
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack).strip()
    return any(pattern in normalized for pattern in _INJECTION_PATTERNS)


@dataclass
class SendPolicy:
    mode: str = REVIEW
    # Contact ids/handles allowed to receive auto-replies (only used when mode == AUTO).
    auto_allowlist: List[str] = field(default_factory=list)
    # Minimum model self-reported confidence [0,1] required to auto-send.
    min_confidence: float = 0.7
    # Never auto-send sensitive/high-stakes content.
    block_sensitive: bool = True
    # Local-hour quiet window [start, end); supports wraparound (e.g. 22 -> 7).
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None

    def normalized_allowlist(self) -> set:
        return {a.strip().lower() for a in self.auto_allowlist if a and a.strip()}


@dataclass
class SendDecision:
    action: str
    reason: str

    @property
    def will_send(self) -> bool:
        return self.action == ACTION_SEND


def _in_quiet_hours(hour: int, start: Optional[int], end: Optional[int]) -> bool:
    if start is None or end is None:
        return False
    start %= 24
    end %= 24
    hour %= 24
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # Wraparound window (e.g. 22:00 -> 07:00).
    return hour >= start or hour < end


def evaluate_send_policy(
    policy: SendPolicy,
    *,
    contact_id: str,
    local_hour: int,
    confidence: float,
    sensitive: bool,
    injection: bool = False,
) -> SendDecision:
    """Decide whether a drafted on-behalf reply may be auto-sent.

    Conservative by default: anything not clearly safe becomes a review draft
    (never silently dropped, never silently sent).
    """
    if policy.mode != AUTO:
        return SendDecision(ACTION_REVIEW, "Review-first mode: the user approves every reply.")

    if contact_id.strip().lower() not in policy.normalized_allowlist():
        return SendDecision(ACTION_REVIEW, "Contact is not on the auto-reply allowlist.")

    if injection:
        return SendDecision(ACTION_REVIEW, "Message looks like a prompt-injection attempt; held for review.")

    if policy.block_sensitive and sensitive:
        return SendDecision(ACTION_REVIEW, "Message looks sensitive or high-stakes; held for review.")

    if confidence < policy.min_confidence:
        return SendDecision(
            ACTION_REVIEW,
            f"Draft confidence {confidence:.2f} is below the auto-send threshold {policy.min_confidence:.2f}.",
        )

    if _in_quiet_hours(local_hour, policy.quiet_hours_start, policy.quiet_hours_end):
        return SendDecision(ACTION_HOLD, "Within quiet hours; will not auto-send right now.")

    return SendDecision(ACTION_SEND, "All auto-reply guardrails passed.")
