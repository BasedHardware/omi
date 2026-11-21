"""Extract payment intent from spoken transcripts and typed /pay commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_WORD = "|".join([*_UNITS, *_TENS, "hundred", "thousand"])
_WORDS = rf"(?:(?:{_WORD})(?:[\s-]+(?:and[\s-]+)?(?=(?:{_WORD})\b))?)+"
_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CURRENCY = r"(?:dollars?|bucks?|usdc|usd)"

_SYMBOL_AMOUNT = re.compile(rf"\$\s?({_NUMBER})", re.I)
_DIGIT_AMOUNT = re.compile(rf"\b({_NUMBER})\s*{_CURRENCY}\b", re.I)
_WORD_AMOUNT = re.compile(
    rf"\b({_WORDS})\s+{_CURRENCY}\b(?:\s+and\s+({_WORDS}|\d+)\s+cents?\b)?", re.I
)
_CENTS_AMOUNT = re.compile(rf"\b({_WORDS}|\d+)\s+cents?\b", re.I)

_SPOKEN_DOT = re.compile(r"(?<=[a-z0-9])\s+dot\s+(?=[a-z])", re.I)
_URL = re.compile(r"\b(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?::\d+)?(?:[/?#][^\s,]*)?", re.I)
_TRIGGER = re.compile(r"\b(pay|send|buy|purchase|subscribe\s+to)\b", re.I)
_CLAUSE_END = re.compile(r"[.!?](?:\s|$)")
_HYPOTHETICAL = re.compile(
    r"\b(?:don'?t|do not|didn'?t|never|not|won'?t|wouldn'?t|can'?t|cannot|would|should|could|"
    r"might|if|had to|forgot to)\b[\w\s']*$",
    re.I,
)
_POSSESSIVE = re.compile(r"\b(?:my|your|his|her|their|our|the|back|take-home)\s*$", re.I)
_COMMAND_PREFIX = re.compile(r"^\s*/?pay\b", re.I)
_MAX_DECIMALS = 6


@dataclass(frozen=True)
class PaymentIntent:
    verb: str
    amount: Decimal | None
    target_url: str | None
    recipient: str | None
    description: str
    raw_text: str

    @property
    def actionable(self) -> bool:
        return self.amount is not None and self.target_url is not None


def words_to_int(text: str) -> int:
    total = current = 0
    for word in re.split(r"[\s-]+", text.lower()):
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word == "thousand":
            total += max(current, 1) * 1000
            current = 0
    return total + current


def _whole(text: str) -> int:
    return int(text) if text.isdigit() else words_to_int(text)


def _decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    # USDC has six decimals; anything finer cannot be paid exactly.
    return value if -value.as_tuple().exponent <= _MAX_DECIMALS else None


def _find_amount(clause: str) -> tuple[Decimal | None, tuple[int, int] | None]:
    for pattern in (_SYMBOL_AMOUNT, _DIGIT_AMOUNT):
        if match := pattern.search(clause):
            return _decimal(match.group(1)), match.span()
    if match := _WORD_AMOUNT.search(clause):
        cents = _whole(match.group(2)) if match.group(2) else 0
        if cents < 100:
            return Decimal(words_to_int(match.group(1))) + Decimal(cents) / 100, match.span()
    if match := _CENTS_AMOUNT.search(clause):
        return Decimal(_whole(match.group(1))) / 100, match.span()
    return None, None


def normalize_url(raw: str) -> str:
    url = raw.rstrip(".,;:!?)")
    return url if re.match(r"https?://", url, re.I) else f"https://{url}"


def _remove(text: str, span: tuple[int, int] | None) -> str:
    return text if span is None else f"{text[:span[0]]} {text[span[1]:]}"


def _describe(verb: str, rest: str) -> tuple[str | None, str]:
    rest = re.sub(r"\s+", " ", rest).strip(" .,!?")
    rest = re.sub(r"\b(?:to|for|at|on|via|from)\s*$", "", rest, flags=re.I).strip()
    recipient_match = re.search(r"\bto\s+(.+?)(?=\s+for\b|$)", rest, re.I)
    purpose_match = re.search(r"\bfor\s+(.+?)(?=\s+to\b|$)", rest, re.I)
    recipient = recipient_match.group(1).strip() if recipient_match else None
    if purpose_match:
        description = purpose_match.group(1).strip()
    else:
        description = re.split(r"\s+(?:to|for)\b", rest, maxsplit=1, flags=re.I)[0].strip()
        description = re.sub(r"\bto\s*$", "", description, flags=re.I).strip()
        if recipient_match and description.lower().startswith("to "):
            description = ""
    if verb == "subscribe to" and not recipient:
        recipient = description or None
    return recipient, description


def parse_intent(text: str) -> PaymentIntent | None:
    """Return the first non-hypothetical payment intent in ``text``, if any."""
    normalized = _SPOKEN_DOT.sub(".", text)
    for trigger in _TRIGGER.finditer(normalized):
        before = normalized[max(0, trigger.start() - 40) : trigger.start()]
        sentence_start = max(before.rfind("."), before.rfind("!"), before.rfind("?"))
        before = before[sentence_start + 1 :]
        if _HYPOTHETICAL.search(before) or _POSSESSIVE.search(before):
            continue

        tail = normalized[trigger.end() :]
        end = _CLAUSE_END.search(tail)
        clause = tail[: end.start()] if end else tail

        url_match = _URL.search(clause)
        target_url = normalize_url(url_match.group(0)) if url_match else None
        without_url = _remove(clause, url_match.span() if url_match else None)
        amount, amount_span = _find_amount(without_url)
        rest = _remove(without_url, amount_span)

        verb = re.sub(r"\s+", " ", trigger.group(1).lower())
        recipient, description = _describe(verb, rest)
        return PaymentIntent(
            verb=verb,
            amount=amount,
            target_url=target_url,
            recipient=recipient,
            description=description,
            raw_text=f"{trigger.group(0)}{clause}".strip(),
        )
    return None


def parse_pay_command(command: str) -> PaymentIntent | None:
    """Parse the text of a /pay command, with or without its leading verb."""
    return parse_intent(f"pay {_COMMAND_PREFIX.sub('', command, count=1).strip()}")
