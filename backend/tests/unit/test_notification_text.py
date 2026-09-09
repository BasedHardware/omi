from pathlib import Path

from testing.import_isolation import load_module_fresh

BACKEND_DIR = Path(__file__).resolve().parents[2]

notification_text = load_module_fresh(
    'utils.notification_text',
    str(BACKEND_DIR / 'utils' / 'notification_text.py'),
)
to_plain_text = notification_text.to_plain_text


def test_strips_bold_and_bullets() -> None:
    assert to_plain_text("- **US President**: Donald Trump") == "• US President: Donald Trump"


def test_strips_headings_code_and_links() -> None:
    assert to_plain_text("## Title\nRun `omi start` and see [the docs](https://omi.me)") == (
        "Title\nRun omi start and see the docs"
    )


def test_keeps_plain_text_and_intra_word_punctuation() -> None:
    body = "Your file_name.txt is 3 * 4 wide and costs $5"
    assert to_plain_text(body) == body


def test_empty_body_is_unchanged() -> None:
    assert to_plain_text('') == ''


def test_flattens_parenthesized_link_and_image_destinations() -> None:
    assert to_plain_text("[Function](https://example.test/wiki/Function_(mathematics))") == "Function"
    assert to_plain_text("[Function](https://example.test/wiki/Function_(mathematics)).") == "Function."
    assert to_plain_text("![Photo](https://example.com/img_(1).png)") == "Photo"
    assert to_plain_text("[Search](https://example.com?q=(test))") == "Search"
    assert to_plain_text("([Function](https://example.test/wiki/Function_(mathematics)))") == "(Function)"
    assert to_plain_text("See [docs](https://omi.me) (version 2.0).") == "See docs (version 2.0)."
    assert to_plain_text("[One](https://a.com(1)) and [Two](https://b.com(2))") == "One and Two"

