import importlib.util
import json
from pathlib import Path
import sqlite3
import zlib

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'scan_wake_word_variants.py'
SPEC = importlib.util.spec_from_file_location('scan_wake_word_variants', SCRIPT_PATH)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


def test_scanner_discovers_followers_cross_segment_gluing_and_compounds_without_raw_text():
    conversations = [
        {
            'id': 'conversation-1',
            'transcript_segments': [
                {'id': 'segment-1', 'text': 'Hey'},
                {'id': 'segment-2', 'text': 'Omni, add a task.'},
            ],
        },
        {
            'id': 'conversation-2',
            'transcript_segments': [{'id': 'segment-3', 'text': 'heyomi remember this'}],
        },
        {
            'id': 'conversation-3',
            'transcript_segments': [{'id': 'segment-4', 'text': 'They buy the OmiLockets device.'}],
        },
        {
            'id': 'conversation-4',
            'transcript_segments': [{'id': 'segment-5', 'text': 'Hey, oh me, add a task.'}],
        },
    ]

    result = scanner.scan_conversations(conversations)

    followers = {item['tokens']: item for item in result['hey_followers']}
    welded = {item['tokens']: item for item in result['welded_hey_suffixes']}
    prefixed = {item['tokens']: item for item in result['omi_prefixed_tokens']}
    assert result['conversations_scanned'] == 4
    assert result['segments_scanned'] == 5
    assert followers['omni']['count'] == 1
    assert followers['omni']['cross_segment_count'] == 1
    assert followers['oh me']['count'] == 1
    assert welded['omi']['count'] == 1
    assert prefixed['omilockets']['count'] == 1
    assert 'conversation-1' not in str(result)
    assert 'add a task' not in str(result)


def test_scanner_accepts_raw_segment_list_as_local_payload():
    conversations = list(scanner._payload_conversations([{'id': 's1', 'text': 'Hey Omi'}]))

    assert conversations == [{'id': 'local-segments', 'transcript_segments': [{'id': 's1', 'text': 'Hey Omi'}]}]


def test_standard_compressed_firestore_shape_decodes_without_encryption_secret():
    segments = [{'id': 's1', 'text': 'Hey Omi'}]
    compressed = zlib.compress(json.dumps(segments).encode('utf-8'))

    assert (
        scanner.decode_firestore_segments(
            {'transcript_segments': compressed, 'transcript_segments_compressed': True},
            'uid-1',
        )
        == segments
    )


def test_enhanced_firestore_shape_requires_a_decrypted_export():
    with pytest.raises(RuntimeError, match='decrypted local export'):
        scanner.decode_firestore_segments(
            {'transcript_segments': 'encrypted', 'transcript_segments_compressed': True},
            'uid-1',
        )


def test_sqlite_loader_reads_transcripts_in_session_order_without_writing(tmp_path):
    database_path = tmp_path / 'omi.db'
    connection = sqlite3.connect(database_path)
    connection.executescript('''
        CREATE TABLE transcription_sessions (
            id INTEGER PRIMARY KEY,
            backendId TEXT,
            clientConversationId TEXT,
            deleted BOOLEAN DEFAULT 0
        );
        CREATE TABLE transcription_segments (
            id INTEGER PRIMARY KEY,
            sessionId INTEGER,
            segmentId TEXT,
            text TEXT,
            startTime DOUBLE,
            endTime DOUBLE,
            segmentOrder INTEGER
        );
        INSERT INTO transcription_sessions (id, backendId) VALUES (1, 'conversation-1');
        INSERT INTO transcription_sessions (id, backendId, deleted) VALUES (2, 'deleted-conversation', 1);
        INSERT INTO transcription_segments VALUES (10, 1, 'segment-2', 'Omni, remember this', 1, 2, 2);
        INSERT INTO transcription_segments VALUES (9, 1, 'segment-1', 'Hey', 0, 1, 1);
        INSERT INTO transcription_segments VALUES (11, 2, 'segment-3', 'Hey Omi', 0, 1, 1);
        ''')
    connection.commit()
    connection.close()

    conversations = list(scanner.load_sqlite_conversations(database_path))

    assert conversations == [
        {
            'id': 'conversation-1',
            'transcript_segments': [
                {'id': 'segment-1', 'text': 'Hey', 'start': 0.0, 'end': 1.0},
                {'id': 'segment-2', 'text': 'Omni, remember this', 'start': 1.0, 'end': 2.0},
            ],
        }
    ]
    assert scanner.scan_conversations(conversations)['hey_followers'][0]['tokens'] == 'omni'
