"""JATS abstracts must be plain text (#13242)."""

from main import clean


def test_clean_strips_jats_paragraph_tags():
    raw = "<jats:p>Sleep quality improved <jats:italic>slightly</jats:italic>.</jats:p>"
    assert clean(raw) == "Sleep quality improved slightly."


def test_clean_unescapes_entities_and_strips_generic_tags():
    assert clean("A &amp; B <b>bold</b>") == "A & B bold"


def test_clean_preserves_inequality_operators():
    assert clean("If a<b, then c>d.") == "If a<b, then c>d."
