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
