"""Safety-first gate for the AI clone / on-behalf responder.

Two layers, deliberately separated so the trust boundary is explicit:

- Safety floor (server-owned, non-negotiable): ``evaluate_safety_floor`` decides whether a
  draft is even eligible to be sent. Sensitive/high-stakes content and prompt-injection
  attempts are always held, and confidence must clear a server-side floor. No client
  request field can weaken this.
- Send authorization (local/persisted policy, layered on top of a passing floor): whether to
  actually auto-send to a given contact (mode, allowlist, quiet hours) is the operator's local
  bridge policy or trusted persisted user settings, never a backend certification derived from
  request-body fields.

All logic here is pure and deterministic so it is fully unit-tested without the LLM or any I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Backend safety-floor verdicts. The backend never certifies "send" from request policy; it
# returns REVIEW (draft cleared the floor, local/persisted policy decides sending) or HOLD
# (draft failed the non-negotiable floor and must not be auto-sent).
ACTION_REVIEW = "review"  # cleared the safety floor; local/persisted policy decides whether to send
ACTION_HOLD = "hold"  # failed the safety floor (sensitive, injection, or low confidence); do not auto-send

# Non-negotiable server-owned confidence floor for auto-send eligibility. A client cannot lower
# this; trusted persisted settings may only raise it.
SERVER_MIN_CONFIDENCE_FLOOR = 0.7

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
class SafetyFloor:
    """Server-owned verdict on whether a draft is eligible to be sent at all."""

    meets_floor: bool
    action: str  # ACTION_REVIEW when the floor is cleared, ACTION_HOLD when it is not
    reason: str


def evaluate_safety_floor(
    *,
    confidence: float,
    sensitive: bool,
    injection: bool,
    min_confidence: float = SERVER_MIN_CONFIDENCE_FLOOR,
) -> SafetyFloor:
    """Non-negotiable pre-send gate owned entirely by the backend.

    A draft is eligible to be sent only if it clears every check here. This is
    independent of any client send policy, so a caller holding the user's token cannot
    weaken it: sensitive/high-stakes content and prompt-injection attempts never clear
    the floor, and confidence must meet a floor of at least SERVER_MIN_CONFIDENCE_FLOOR
    (trusted persisted settings may raise it, never lower it). Whether a cleared draft is
    actually auto-sent to a given contact (mode, allowlist, quiet hours) is a separate
    local/persisted decision layered on top of a passing floor.
    """
    floor = max(min_confidence, SERVER_MIN_CONFIDENCE_FLOOR)
    if injection:
        return SafetyFloor(False, ACTION_HOLD, "Message looks like a prompt-injection attempt; held for review.")
    if sensitive:
        return SafetyFloor(False, ACTION_HOLD, "Message looks sensitive or high-stakes; held for review.")
    if confidence < floor:
        return SafetyFloor(
            False,
            ACTION_HOLD,
            f"Draft confidence {confidence:.2f} is below the safety floor {floor:.2f}.",
        )
    return SafetyFloor(
        True,
        ACTION_REVIEW,
        "Draft cleared the safety floor; whether to send is a local or persisted policy decision.",
    )
