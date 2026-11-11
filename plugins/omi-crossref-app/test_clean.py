"""JATS abstracts and Crossref titles must be plain text (#13242, #14307)."""

from main import clean


def test_clean_strips_jats_paragraph_tags():
    raw = "<jats:p>Sleep quality improved <jats:italic>slightly</jats:italic>.</jats:p>"
    assert clean(raw) == "Sleep quality improved slightly."


def test_clean_unescapes_entities_and_strips_generic_tags():
    assert clean("A &amp; B <b>bold</b>") == "A & B bold"


def test_clean_preserves_inequality_operators():
    assert clean("If a<b, then c>d.") == "If a<b, then c>d."


def test_clean_strips_closing_tags_after_word_chars():
    assert clean("text</p> tail") == "text tail"
    assert clean("A &amp; B <b>bold</b>") == "A & B bold"
def test_clean_strips_word_adjacent_face_markup_tags():
    assert clean("H<sub>2</sub>O") == "H2O"
    assert clean("x<sup>y<sup>z</sup></sup>") == "xyz"
    assert clean("CO<sub>2</sub> emissions in 2020") == "CO2 emissions in 2020"
    assert clean("E=mc<sup>2</sup>") == "E=mc2"
    assert clean("Drug-A<sub>1</sub> and Drug-B<sup>2</sup>") == "Drug-A1 and Drug-B2"


def test_clean_strips_face_markup_with_attributes():
    assert clean('<font color="red">Sample Title</font>') == "Sample Title"
    assert clean("<i>Italicized</i> species: <b>Escherichia coli</b>") == "Italicized species: Escherichia coli"


def test_clean_preserves_encoded_and_raw_inequalities():
    # Encoded chained comparison must preserve <b> rather than stripping as a tag (#14307 review)
    assert clean("If a&lt;b&gt;c, continue.") == "If a<b>c, continue."
    assert clean("When x &lt; y and y &gt; z.") == "When x < y and y > z."
