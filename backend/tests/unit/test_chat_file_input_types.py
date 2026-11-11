"""Allowlist for Chat Completions file inputs: extension first, MIME second.

External source: OpenAI File inputs "Accepted file types" / full extension-MIME
table, read 2026-09-08 (saved copy used by #13200).
"""

from datetime import datetime, timezone

from models.chat import FileChat, chat_file_is_document


def test_extension_is_checked_before_mime():
    assert chat_file_is_document('note.txt', 'application/zip') is True
    assert chat_file_is_document('archive.zip', 'text/plain') is False
    assert chat_file_is_document('note.pdf', 'text/plain') is True
    assert chat_file_is_document('Report.PDF', 'application/zip') is True


def test_uppercase_extension_is_allowlisted():
    assert chat_file_is_document('NOTE.TXT', '') is True
    assert chat_file_is_document('Brief.DOCX', 'None') is True
    assert chat_file_is_document('Report.PDF', 'None') is True


def test_missing_mime_string_none_does_not_admit_or_reject():
    # File.get_mime_type stores str(None) == 'None' when guess_type fails.
    assert chat_file_is_document('note.txt', 'None') is True
    assert chat_file_is_document('note.txt', None) is True
    assert chat_file_is_document('archive.zip', 'None') is False
    assert chat_file_is_document('archive.bin', None) is False


def test_mime_admits_when_extension_is_absent():
    assert chat_file_is_document('untitled', 'text/plain') is True
    assert chat_file_is_document('untitled', 'application/pdf') is True
    assert chat_file_is_document('untitled', '') is False


def test_documented_mime_only_suffixes_are_allowlisted():
    # The provider's MIME column documents types whose canonical suffixes are
    # missing from its Extensions column; the extension allowlist covers them
    # so the extension-first branch cannot reject a documented type.
    assert chat_file_is_document('main.rs', 'text/x-rust') is True
    assert chat_file_is_document('config.yaml', 'text/x-yaml') is True
    assert chat_file_is_document('app.ts', 'text/x-typescript') is True
    assert chat_file_is_document('script.scala', 'text/x-scala') is True
    assert chat_file_is_document('pack.proto', 'text/x-protobuf') is True
    assert chat_file_is_document('site.astro', 'text/x-astro') is True


def test_undocumented_suffixes_stay_rejected():
    assert chat_file_is_document('archive.zip', 'text/plain') is False
    assert chat_file_is_document('movie.mp4', 'text/plain') is False
    assert chat_file_is_document('database.db', 'text/plain') is False


def test_filechat_is_document_includes_pdf_and_txt():
    now = datetime.now(timezone.utc)
    pdf = FileChat(id='1', name='a.pdf', mime_type='application/pdf', openai_file_id='f1', created_at=now)
    txt = FileChat(id='2', name='a.txt', mime_type='text/plain', openai_file_id='f2', created_at=now)
    ogg = FileChat(id='3', name='note.ogg', mime_type='audio/ogg', openai_file_id='f3', created_at=now)
    assert pdf.is_document() is True
    assert txt.is_document() is True
    assert ogg.is_document() is False
