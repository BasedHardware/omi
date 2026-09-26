"""Canonical transcript_sha256: identity+text, order-sensitive, client-reproducible.

Red-proofs (one-line mutation that would make the named assertion pass wrongly):
- omit speaker from the framed payload (swapped attribution would hash identically)
- omit speaker_id from the framed payload (Speaker 0 vs Speaker 7 would match)
- omit is_user / person_id from the framed payload (user vs Alice vs Bob would match)
- join with newline instead of length-framing (['a\\nb'] collides with ['a','b'])
- length-frame only text (speaker='ab' text='c' collides with speaker='a' text='bc')
- drop .strip() (padded text/speaker/person_id would hash as a different conversation)
- default missing speaker to SPEAKER_00 (dicts without speaker would match TranscriptSegment)
- default missing speaker_id to 0 without deriving from SPEAKER_07 (dict vs model would diverge)
- default missing is_user to False / missing person_id to empty (dict vs model would diverge)
- require TranscriptSegment only (dicts / request models would fail)
- persist raw person_id / speaker at ingest (alice vs ' alice ' would share a digest
  and render Alice vs Speaker 0)
- skip empty-after-strip segments in the framed payload (['approved transfer']
  would share a digest with that plus empty SPEAKER_07, while rendering adds
  'Speaker 7:')
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.conversations.transcript_hash import (
    DEFAULT_SPEAKER,
    DEFAULT_SPEAKER_ID,
    TRANSCRIPT_HASH_ENCODING_VERSION,
    canonical_segment,
    stored_transcript_segment,
    transcript_sha256,
    transcript_sha256_for_binding,
)

# Known-answer vector (encoding v5). Client implementers: hash these segments,
# expect this hex. Canonical bytes are length-framed (speaker, speaker_id,
# is_user token, person_id, text) tuples. An omitted speaker is SPEAKER_00, an
# omitted speaker_id is the id TranscriptSegment materializes from that label
# (0 here: Alice/Bob do not carry a trailing decimal), an omitted is_user is
# not-user (N), an omitted person_id is the empty frame -- the same values the
# segment models materialize -- so a client hashing its own JSON gets the
# server's digest. Empty-after-strip text still contributes those identity
# frames; only an empty list hashes the empty byte string.
KNOWN_ANSWER_SEGMENTS = [
    {'speaker': 'Alice', 'text': 'I agree'},
    {'speaker': 'Bob', 'text': 'I refuse'},
]
KNOWN_ANSWER_CANONICAL = b'5\nAlice1\n01\nN0\n7\nI agree3\nBob1\n01\nN0\n8\nI refuse'
KNOWN_ANSWER_DIGEST = '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40'

HELLO_WORLD_CANONICAL = b'10\nSPEAKER_001\n01\nN0\n5\nhello10\nSPEAKER_001\n01\nN0\n5\nworld'
HELLO_WORLD_DIGEST = '8c07ee1d1a21bd1f1f319362b1435d6e875f8e24ef326dc08ecf113e226e3410'
EMPTY_DIGEST = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
UNICODE_CANONICAL = b'10\nSPEAKER_001\n01\nN0\n12\ncaf\xc3\xa9 \xe4\xbd\xa0\xe5\xa5\xbd'
UNICODE_DIGEST = 'de349219ac8122fb4f1bd000167d933ed6657dff1ad3835e1deb06a2bf79eef5'

# Reviewer's reproduction: same SPEAKER_00 label, same words, three identities.
TRANSFER_TEXT = 'I approved the transfer'
TRANSFER_USER_CANONICAL = b'10\nSPEAKER_001\n01\nY0\n23\nI approved the transfer'
TRANSFER_USER_DIGEST = '51d7fb6fb4e3cf863a1210d21280cbfb91e8dd16d818d9d6208af00470a5e3c9'
TRANSFER_ALICE_CANONICAL = b'10\nSPEAKER_001\n01\nN5\nalice23\nI approved the transfer'
TRANSFER_ALICE_DIGEST = '55629d482ae03ac3ca5f315ff39a6ac156e1ada4e4f6428b2a6fb9ec88b36a8d'
TRANSFER_BOB_CANONICAL = b'10\nSPEAKER_001\n01\nN3\nbob23\nI approved the transfer'
TRANSFER_BOB_DIGEST = 'f98fe02c6d6dc10c77bba8cb835aaf5064cc24add2b4af2a09a6fb43aae19224'

# Reviewer's v4 reproduction: same label, same words, speaker_id 0 vs 7.
TRANSFER_SPEAKER_0_CANONICAL = b'10\nSPEAKER_001\n01\nN0\n23\nI approved the transfer'
TRANSFER_SPEAKER_0_DIGEST = '863cf7938e692d22b06f5b757ad5330a517c87f60d115e5dd97a973fbc248d50'
TRANSFER_SPEAKER_7_CANONICAL = b'10\nSPEAKER_001\n71\nN0\n23\nI approved the transfer'
TRANSFER_SPEAKER_7_DIGEST = 'd7dfcd646cda9e7d068693db981c82e11d144d376c800ba0640b611d3768ecdf'

# Reviewer's v5 reproduction: empty-after-strip SPEAKER_07 still frames identity.
EMPTY_SEGMENT_CANONICAL = b'10\nSPEAKER_001\n01\nN0\n0\n'
EMPTY_SEGMENT_DIGEST = '1f4edaaa8c0b550ed42040ed654a8bccfd34e121da991f1b986f9821e3d360a8'
APPROVED_TRANSFER_CANONICAL = b'10\nSPEAKER_001\n01\nN0\n17\napproved transfer'
APPROVED_TRANSFER_DIGEST = '297706a799a1cbb3972cbabb26dd87e6cbcf15a3da5dbd28de169017cbbe5879'
EMPTY_SPEAKER_07_CANONICAL = b'10\nSPEAKER_071\n71\nN0\n0\n'
APPROVED_PLUS_EMPTY_07_CANONICAL = APPROVED_TRANSFER_CANONICAL + EMPTY_SPEAKER_07_CANONICAL
APPROVED_PLUS_EMPTY_07_DIGEST = '4d531124f58691011f68664c6f6c7ba79c1822d9d33372df2c0c507cdd69eedc'


def _seg(
    text: str,
    *,
    speaker: str = 'SPEAKER_00',
    speaker_id: int | None = None,
    start: float = 0.0,
    end: float = 1.0,
    is_user: bool = False,
    person_id: str | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(
        text=text,
        speaker=speaker,
        speaker_id=speaker_id,
        start=start,
        end=end,
        is_user=is_user,
        person_id=person_id,
    )


def test_encoding_version_is_v5() -> None:
    # Encoding v5 still binds (speaker, speaker_id, is_user, person_id, text)
    # per segment, and now includes empty-after-strip text. v4 skipped those
    # rows, so ['approved transfer'] hashed identically to that transcript
    # plus an empty SPEAKER_07 while rendering added 'Speaker 7:'.
    assert TRANSCRIPT_HASH_ENCODING_VERSION == 5


def test_known_answer_vector_pins_input_to_hex() -> None:
    # red-proof: omit speaker / speaker_id / identity frames (this digest is sha256 of the v5 canonical bytes)
    assert KNOWN_ANSWER_CANONICAL == b'5\nAlice1\n01\nN0\n7\nI agree3\nBob1\n01\nN0\n8\nI refuse'
    assert KNOWN_ANSWER_DIGEST == '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40'
    assert sha256(KNOWN_ANSWER_CANONICAL).hexdigest() == KNOWN_ANSWER_DIGEST
    assert transcript_sha256(KNOWN_ANSWER_SEGMENTS) == KNOWN_ANSWER_DIGEST
    assert transcript_sha256([_seg('I agree', speaker='Alice'), _seg('I refuse', speaker='Bob')]) == KNOWN_ANSWER_DIGEST


def test_swapped_attribution_changes_the_digest() -> None:
    # red-proof: hash text only (Alice/Bob vs Bob/Alice would match)
    original = transcript_sha256(KNOWN_ANSWER_SEGMENTS)
    swapped = transcript_sha256(
        [
            {'speaker': 'Bob', 'text': 'I agree'},
            {'speaker': 'Alice', 'text': 'I refuse'},
        ]
    )
    assert original != swapped
    assert original == KNOWN_ANSWER_DIGEST
    assert swapped == '5f6defd143d278a1d42ff08a8e568bcf0e047d9653241ad10b6d0fa0d8b44240'


def test_empty_list_hashes_empty_string() -> None:
    # Only an empty list is the empty transcript. Empty-after-strip *rows*
    # still contribute identity frames (v5).
    assert transcript_sha256([]) == EMPTY_DIGEST
    assert sha256(b'').hexdigest() == EMPTY_DIGEST
    assert transcript_sha256([{'text': ''}]) == EMPTY_SEGMENT_DIGEST
    assert transcript_sha256([{'text': '   '}]) == EMPTY_SEGMENT_DIGEST
    assert transcript_sha256([{'text': ''}]) != EMPTY_DIGEST
    assert transcript_sha256([{'speaker': 'Alice', 'text': ''}, {'speaker': 'Bob', 'text': '   '}]) != EMPTY_DIGEST


def test_timings_are_ignored() -> None:
    left = transcript_sha256(
        [
            _seg('I agree', speaker='Alice', start=0.0, end=1.0),
            _seg('I refuse', speaker='Bob', start=9.0, end=12.5),
        ]
    )
    right = transcript_sha256(
        [
            _seg('I agree', speaker='Alice', start=100.0, end=101.0),
            _seg('I refuse', speaker='Bob', start=0.1, end=0.2),
        ]
    )
    assert left == right == KNOWN_ANSWER_DIGEST


def test_absent_speaker_canonicalizes_to_the_model_default() -> None:
    """Missing / None / blank speaker all mean SPEAKER_00, like the models.

    red-proof: return '' instead of DEFAULT_SPEAKER for an absent speaker --
    then the dict form stops matching the parsed model and every client-computed
    digest misses.
    """
    missing = transcript_sha256([{'text': 'hello'}, {'text': 'world'}])
    none_speaker = transcript_sha256([{'speaker': None, 'text': 'hello'}, {'speaker': None, 'text': 'world'}])
    empty = transcript_sha256([{'speaker': '', 'text': 'hello'}, {'speaker': '', 'text': 'world'}])
    whitespace = transcript_sha256([{'speaker': '  ', 'text': 'hello'}, {'speaker': '\n\t', 'text': 'world'}])
    labelled = transcript_sha256(
        [{'speaker': 'SPEAKER_00', 'text': 'hello'}, {'speaker': 'SPEAKER_00', 'text': 'world'}]
    )
    # An omitted speaker and an explicit SPEAKER_00 are the SAME transcript.
    assert missing == none_speaker == empty == whitespace == labelled == HELLO_WORLD_DIGEST
    assert labelled == transcript_sha256([_seg('hello'), _seg('world')])
    # A different label is a different transcript, and 'unknown' is not the default.
    unknown = transcript_sha256([{'speaker': 'unknown', 'text': 'hello'}, {'speaker': 'unknown', 'text': 'world'}])
    other = transcript_sha256([{'speaker': 'SPEAKER_01', 'text': 'hello'}, {'speaker': 'SPEAKER_01', 'text': 'world'}])
    assert unknown != HELLO_WORLD_DIGEST
    assert other != HELLO_WORLD_DIGEST
    assert unknown != other


def test_order_is_significant() -> None:
    forward = transcript_sha256([{'text': 'hello'}, {'text': 'world'}])
    reverse = transcript_sha256([{'text': 'world'}, {'text': 'hello'}])
    assert forward != reverse
    assert forward == HELLO_WORLD_DIGEST


def test_whitespace_is_stripped_per_segment() -> None:
    # red-proof: drop .strip() (padding would change the digest)
    padded = transcript_sha256([{'text': '  hello  '}, {'text': '\nworld\t'}])
    assert padded == HELLO_WORLD_DIGEST
    padded_speakers = transcript_sha256(
        [
            {'speaker': '  Alice  ', 'text': '  I agree  '},
            {'speaker': '\nBob\t', 'text': 'I refuse'},
        ]
    )
    assert padded_speakers == KNOWN_ANSWER_DIGEST
    # Internal whitespace is preserved and length-framed.
    assert (
        transcript_sha256([{'text': 'hello  world'}])
        == sha256(b'10\nSPEAKER_001\n01\nN0\n12\nhello  world').hexdigest()
    )
    # Stripping the label happens before speaker_id is derived, so a padded
    # SPEAKER_07 materializes the same id as the stored SPEAKER_07 model.
    padded_slot = transcript_sha256([{'speaker': '  SPEAKER_07  ', 'text': 'hello'}])
    clean_slot = transcript_sha256([{'speaker': 'SPEAKER_07', 'text': 'hello'}])
    assert padded_slot == clean_slot == transcript_sha256([_seg('hello', speaker='SPEAKER_07')])


def test_empty_after_strip_segments_still_contribute_identity_frames() -> None:
    # red-proof: skip empty-after-strip parts (['hello','world'] would match
    # that transcript with empty rows interleaved, and ['approved transfer']
    # would match that plus empty SPEAKER_07).
    assert transcript_sha256([{'text': ''}]) == EMPTY_SEGMENT_DIGEST
    assert sha256(EMPTY_SEGMENT_CANONICAL).hexdigest() == EMPTY_SEGMENT_DIGEST
    assert (
        transcript_sha256([{'text': 'hello'}, {'text': ''}, {'text': '   '}, {'text': 'world'}]) != HELLO_WORLD_DIGEST
    )
    assert transcript_sha256([{'text': None}, {'text': 'hello'}, {}, {'text': 'world'}]) != HELLO_WORLD_DIGEST
    assert stored_transcript_segment({'text': '', 'speaker': 'SPEAKER_07'}) is None
    assert stored_transcript_segment({'text': '   ', 'speaker': 'SPEAKER_07'}) is None
    approved = [{'text': _RENDER_TEXT}]
    approved_plus_empty = [{'text': _RENDER_TEXT}, {'speaker': 'SPEAKER_07', 'text': ''}]
    assert transcript_sha256(approved) == APPROVED_TRANSFER_DIGEST
    assert transcript_sha256(approved_plus_empty) == APPROVED_PLUS_EMPTY_07_DIGEST
    assert transcript_sha256(approved) != transcript_sha256(approved_plus_empty)
    assert sha256(APPROVED_TRANSFER_CANONICAL).hexdigest() == APPROVED_TRANSFER_DIGEST
    assert sha256(APPROVED_PLUS_EMPTY_07_CANONICAL).hexdigest() == APPROVED_PLUS_EMPTY_07_DIGEST
    assert sha256(EMPTY_SPEAKER_07_CANONICAL).hexdigest() == transcript_sha256([{'speaker': 'SPEAKER_07', 'text': ''}])


def test_accepts_transcript_segment_request_models_and_dicts() -> None:
    class RequestSegment:
        def __init__(self, text: str, speaker: str = '', start: float = 0.0):
            self.text = text
            self.speaker = speaker
            self.start = start
            self.end = start + 1.0
            self.is_user = False

    mixed = [
        SimpleNamespace(text='hello', speaker=''),
        RequestSegment('world'),
    ]
    assert transcript_sha256(mixed) == HELLO_WORLD_DIGEST
    assert transcript_sha256([SimpleNamespace(text='hello'), SimpleNamespace(text='world')]) == HELLO_WORLD_DIGEST
    assert transcript_sha256([{'text': 'hello', 'speaker': '', 'start': 1.5}, {'text': 'world'}]) == HELLO_WORLD_DIGEST


def test_unicode_is_hashed_as_utf8() -> None:
    assert UNICODE_CANONICAL == b'10\nSPEAKER_001\n01\nN0\n12\n' + 'café 你好'.encode('utf-8')
    assert transcript_sha256([{'text': 'café 你好'}]) == UNICODE_DIGEST
    assert UNICODE_DIGEST == sha256(UNICODE_CANONICAL).hexdigest()


def test_newline_inside_segment_does_not_collide_with_two_segments() -> None:
    # Reviewer's case: join-with-newline hashed these identically.
    # red-proof: return sha256('\\n'.join(parts).encode('utf-8')).hexdigest()
    one = transcript_sha256([{'text': 'a\nb'}])
    two = transcript_sha256([{'text': 'a'}, {'text': 'b'}])
    assert one != two
    assert one == sha256(b'10\nSPEAKER_001\n01\nN0\n3\na\nb').hexdigest()
    assert two == sha256(b'10\nSPEAKER_001\n01\nN0\n1\na10\nSPEAKER_001\n01\nN0\n1\nb').hexdigest()


def test_speaker_and_text_bytes_cannot_be_moved_to_collide() -> None:
    # red-proof: length-frame only the concatenated speaker+text (these would match)
    moved = transcript_sha256([{'speaker': 'ab', 'text': 'c'}])
    original = transcript_sha256([{'speaker': 'a', 'text': 'bc'}])
    assert moved != original
    newline_speaker = transcript_sha256([{'speaker': 'a\n1', 'text': 'b'}])
    newline_text = transcript_sha256([{'speaker': 'a', 'text': '1\nb'}])
    assert newline_speaker != newline_text
    assert moved == sha256(b'2\nab1\n01\nN0\n1\nc').hexdigest()
    assert original == sha256(b'1\na1\n01\nN0\n2\nbc').hexdigest()


def test_dict_without_speaker_matches_the_model_default_so_clients_can_reproduce_it() -> None:
    """A client hashing its own JSON must land on the server's digest.

    TranscriptSegment and the request segment models materialize SPEAKER_00 for
    an omitted speaker. If the raw-dict path hashed a missing speaker as the
    empty string instead, every projection from a client that omits the field
    would be dropped for a hash mismatch -- silently, with the conversation
    still landing and no error raised anywhere.
    """
    dict_no_speaker = [{'text': 'hello'}]
    dict_explicit = [{'text': 'hello', 'speaker': DEFAULT_SPEAKER}]
    model_default = [TranscriptSegment(text='hello', start=0.0, end=1.0, is_user=False)]

    assert transcript_sha256(dict_no_speaker) == transcript_sha256(model_default)
    assert transcript_sha256(dict_explicit) == transcript_sha256(model_default)
    assert transcript_sha256([{'text': 'hello', 'speaker': 'SPEAKER_01'}]) != transcript_sha256(model_default)


def test_same_label_user_alice_bob_produce_three_digests() -> None:
    """SPEAKER_00 is a diarization slot, not a person.

        red-proof: hash only (speaker, text) -- all three of these were identical
    under encoding v2 when the label stayed SPEAKER_00.
    """
    user = [{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'is_user': True}]
    alice = [{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'is_user': False, 'person_id': 'alice'}]
    bob = [{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'is_user': False, 'person_id': 'bob'}]

    user_digest = transcript_sha256(user)
    alice_digest = transcript_sha256(alice)
    bob_digest = transcript_sha256(bob)

    assert user_digest != alice_digest != bob_digest
    assert user_digest != bob_digest
    assert user_digest == TRANSFER_USER_DIGEST
    assert alice_digest == TRANSFER_ALICE_DIGEST
    assert bob_digest == TRANSFER_BOB_DIGEST
    assert sha256(TRANSFER_USER_CANONICAL).hexdigest() == TRANSFER_USER_DIGEST
    assert sha256(TRANSFER_ALICE_CANONICAL).hexdigest() == TRANSFER_ALICE_DIGEST
    assert sha256(TRANSFER_BOB_CANONICAL).hexdigest() == TRANSFER_BOB_DIGEST
    # The parsed-model form of each identity agrees with the dict form.
    assert transcript_sha256([_seg(TRANSFER_TEXT, is_user=True)]) == user_digest
    assert transcript_sha256([_seg(TRANSFER_TEXT, person_id='alice')]) == alice_digest
    assert transcript_sha256([_seg(TRANSFER_TEXT, person_id='bob')]) == bob_digest


def test_reassigning_person_id_changes_the_digest() -> None:
    # red-proof: skip the person_id frame (reassignment would keep verifying)
    original = transcript_sha256([{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'person_id': 'alice'}])
    reassigned = transcript_sha256([{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'person_id': 'carol'}])
    assert original != reassigned
    assert original == TRANSFER_ALICE_DIGEST
    assert original == transcript_sha256([_seg(TRANSFER_TEXT, person_id='alice')])
    assert reassigned == transcript_sha256([_seg(TRANSFER_TEXT, person_id='carol')])


def test_absent_is_user_and_person_id_canonicalizes_to_the_model_default() -> None:
    """Omitted is_user is False; omitted person_id is None -- like the models.

    red-proof: treat a missing is_user as True, or a missing person_id as a
    sentinel other than the empty frame -- dict JSON would stop matching
    TranscriptSegment / DevTranscriptSegment defaults.
    """
    omitted = transcript_sha256([{'text': 'hello'}])
    explicit_false = transcript_sha256([{'text': 'hello', 'is_user': False, 'person_id': None}])
    model = transcript_sha256([_seg('hello')])
    assert omitted == explicit_false == model == sha256(b'10\nSPEAKER_001\n01\nN0\n5\nhello').hexdigest()
    # Only an actual True counts; 1 and "true" are not-user (the default).
    assert transcript_sha256([{'text': 'hello', 'is_user': 1}]) == omitted
    assert transcript_sha256([{'text': 'hello', 'is_user': 'true'}]) == omitted
    assert transcript_sha256([{'text': 'hello', 'is_user': True}]) != omitted
    # Empty / whitespace person_id is the same as omitted, and differs from a present id.
    empty_pid = transcript_sha256([{'text': 'hello', 'person_id': ''}])
    whitespace_pid = transcript_sha256([{'text': 'hello', 'person_id': '   '}])
    present = transcript_sha256([{'text': 'hello', 'person_id': 'alice'}])
    assert empty_pid == whitespace_pid == omitted
    assert present != omitted
    # A present id of "0" is not the empty frame.
    assert transcript_sha256([{'text': 'hello', 'person_id': '0'}]) != omitted


def test_identity_bytes_cannot_be_moved_between_fields() -> None:
    """Length-framing keeps is_user / person_id / text from impersonating each other.

    red-proof: concatenate identity+text without per-field length prefixes.
    """
    # is_user token Y + empty person_id vs not-user + person_id "Y"
    as_user = transcript_sha256([{'text': 'hi', 'is_user': True}])
    person_named_y = transcript_sha256([{'text': 'hi', 'is_user': False, 'person_id': 'Y'}])
    assert as_user != person_named_y
    # person_id vs text
    pid_ab_text_c = transcript_sha256([{'text': 'c', 'person_id': 'ab'}])
    pid_a_text_bc = transcript_sha256([{'text': 'bc', 'person_id': 'a'}])
    assert pid_ab_text_c != pid_a_text_bc
    # speaker vs is_user token
    speaker_y = transcript_sha256([{'speaker': 'Y', 'text': 'hi'}])
    user_default_speaker = transcript_sha256([{'text': 'hi', 'is_user': True}])
    assert speaker_y != user_default_speaker
    # speaker_id vs person_id / text / speaker (the v4 frames)
    sid_seven = transcript_sha256([{'text': 'hi', 'speaker_id': 7}])
    person_named_seven = transcript_sha256([{'text': 'hi', 'person_id': '7'}])
    text_seven = transcript_sha256([{'text': '7'}])
    speaker_seven = transcript_sha256([{'speaker': '7', 'text': 'hi'}])
    assert sid_seven != person_named_seven
    assert sid_seven != text_seven
    assert sid_seven != speaker_seven
    # speaker vs speaker_id are adjacent; without per-field length prefixes
    # speaker='12' speaker_id=3 collides with speaker='1' speaker_id=23.
    speaker_12_id_3 = transcript_sha256([{'speaker': '12', 'text': 'x', 'speaker_id': 3}])
    speaker_1_id_23 = transcript_sha256([{'speaker': '1', 'text': 'x', 'speaker_id': 23}])
    assert speaker_12_id_3 != speaker_1_id_23


def test_speaker_id_zero_versus_seven_differ_with_everything_else_equal() -> None:
    """Rendering shows 'Speaker 0' vs 'Speaker 7'; the digest must too.

    red-proof: skip the speaker_id frame -- v3 hashed these identically.
    """
    as_zero = [{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'speaker_id': 0}]
    as_seven = [{'speaker': 'SPEAKER_00', 'text': TRANSFER_TEXT, 'speaker_id': 7}]
    zero_digest = transcript_sha256(as_zero)
    seven_digest = transcript_sha256(as_seven)
    assert zero_digest != seven_digest
    assert zero_digest == TRANSFER_SPEAKER_0_DIGEST
    assert seven_digest == TRANSFER_SPEAKER_7_DIGEST
    assert sha256(TRANSFER_SPEAKER_0_CANONICAL).hexdigest() == TRANSFER_SPEAKER_0_DIGEST
    assert sha256(TRANSFER_SPEAKER_7_CANONICAL).hexdigest() == TRANSFER_SPEAKER_7_DIGEST
    assert transcript_sha256([_seg(TRANSFER_TEXT, speaker_id=0)]) == zero_digest
    assert transcript_sha256([_seg(TRANSFER_TEXT, speaker_id=7)]) == seven_digest


def test_absent_speaker_id_canonicalizes_to_the_model_default() -> None:
    """Omitted speaker_id is the int TranscriptSegment materializes.

    red-proof: hard-code missing speaker_id as 0 even for SPEAKER_07 -- then a
    client hashing JSON with speaker=SPEAKER_07 and no speaker_id key misses
    the server digest of the parsed model (which sets speaker_id=7).
    """
    omitted = transcript_sha256([{'text': 'hello'}])
    explicit_zero = transcript_sha256([{'text': 'hello', 'speaker_id': DEFAULT_SPEAKER_ID}])
    none_id = transcript_sha256([{'text': 'hello', 'speaker_id': None}])
    model = transcript_sha256([_seg('hello')])
    assert omitted == explicit_zero == none_id == model
    assert _seg('hello').speaker_id == DEFAULT_SPEAKER_ID
    # Only an actual int counts; bool is an int subclass and must not win.
    assert transcript_sha256([{'text': 'hello', 'speaker_id': False}]) == omitted
    assert transcript_sha256([{'text': 'hello', 'speaker_id': True}]) == omitted
    assert transcript_sha256([{'text': 'hello', 'speaker_id': '7'}]) == omitted
    assert transcript_sha256([{'text': 'hello', 'speaker_id': 7}]) != omitted
    # SPEAKER_07 with no speaker_id materializes 7, matching the parsed model.
    derived_dict = [{'speaker': 'SPEAKER_07', 'text': 'hello'}]
    derived_model = _seg('hello', speaker='SPEAKER_07')
    assert derived_model.speaker_id == 7
    assert transcript_sha256(derived_dict) == transcript_sha256([derived_model])
    assert transcript_sha256(derived_dict) != omitted


def test_dict_and_model_agree_for_every_identity_field() -> None:
    """A client hashing its own JSON must match the parsed-model digest.

    red-proof: hash getattr(segment, 'speaker_id', 0) without deriving from the
    label -- DevTranscriptSegment / a JSON dict with speaker=SPEAKER_07 and no
    speaker_id key would then disagree with TranscriptSegment.
    """
    cases: list[tuple[dict[str, object], TranscriptSegment]] = [
        ({'text': 'hello'}, _seg('hello')),
        ({'text': 'hello', 'speaker': DEFAULT_SPEAKER}, _seg('hello', speaker=DEFAULT_SPEAKER)),
        ({'text': 'hello', 'speaker': 'SPEAKER_07'}, _seg('hello', speaker='SPEAKER_07')),
        ({'text': 'hello', 'speaker_id': 0}, _seg('hello', speaker_id=0)),
        ({'text': 'hello', 'speaker_id': 7}, _seg('hello', speaker_id=7)),
        ({'text': 'hello', 'is_user': True}, _seg('hello', is_user=True)),
        ({'text': 'hello', 'person_id': 'alice'}, _seg('hello', person_id='alice')),
        (
            {
                'text': TRANSFER_TEXT,
                'speaker': 'SPEAKER_00',
                'speaker_id': 7,
                'is_user': False,
                'person_id': 'bob',
            },
            _seg(TRANSFER_TEXT, speaker_id=7, person_id='bob'),
        ),
        ({'text': '', 'speaker': 'SPEAKER_07'}, _seg('', speaker='SPEAKER_07')),
        ({'text': '   ', 'speaker': 'SPEAKER_07'}, _seg('', speaker='SPEAKER_07')),
    ]
    for payload, model in cases:
        assert transcript_sha256([payload]) == transcript_sha256([model])
        stored = stored_transcript_segment(payload)
        if stored is None:
            assert canonical_segment(payload).text == ''
            continue
        assert transcript_sha256([payload]) == transcript_sha256([stored])


_RENDER_PEOPLE = [
    Person(id='alice', name='Alice'),
    Person(id='bob', name='Bob'),
]
_RENDER_TEXT = 'approved transfer'


def _store(payload: dict[str, object]) -> TranscriptSegment:
    stored = stored_transcript_segment(payload)
    if stored is not None:
        return stored
    # from-segments 422s empty text; live capture and sync keep the row.
    kept = canonical_segment(payload)
    return TranscriptSegment(
        text=kept.text,
        speaker=kept.speaker,
        speaker_id=kept.speaker_id,
        is_user=kept.is_user,
        person_id=kept.person_id,
        start=0.0,
        end=1.0,
    )


def _render_transcript(segments: list[TranscriptSegment]) -> str:
    return TranscriptSegment.segments_as_string(segments, user_name='You', people=_RENDER_PEOPLE)


def _render(stored: TranscriptSegment) -> str:
    return _render_transcript([stored])


def test_equal_digests_imply_identical_rendered_attribution() -> None:
    """Hash equality implies identical rendered attribution.

    Reviewer's reproduction: hashing stripped person_id 'alice' and ' alice '
    to the same digest while from-segments stored the raw value, so rendering
    produced 'Alice: approved transfer' versus 'Speaker 0: approved transfer'.

    red-proof: persist ``person_id`` / ``speaker`` without canonical_segment
    (``person_id=payload['person_id']`` on TranscriptSegment) -- then the
    padded/unpadded pairs below share a digest and display different speakers.
    red-proof: skip empty-after-strip segments in the framed payload -- then
    ``['approved transfer']`` and that transcript plus empty SPEAKER_07
    share a digest while the renderer adds ``Speaker 7:``.
    """
    same_transcript_pairs: list[tuple[dict[str, object], dict[str, object]]] = [
        (
            {'text': _RENDER_TEXT, 'person_id': 'alice'},
            {'text': _RENDER_TEXT, 'person_id': ' alice '},
        ),
        (
            {'text': _RENDER_TEXT, 'person_id': 'alice'},
            {'text': _RENDER_TEXT, 'person_id': '\talice\n'},
        ),
        (
            {'text': _RENDER_TEXT, 'speaker': 'SPEAKER_07'},
            {'text': _RENDER_TEXT, 'speaker': '  SPEAKER_07  '},
        ),
        (
            {'text': _RENDER_TEXT, 'speaker': 'Alice'},
            {'text': _RENDER_TEXT, 'speaker': '  Alice  '},
        ),
        (
            {'text': _RENDER_TEXT, 'is_user': True},
            {'text': f'  {_RENDER_TEXT}  ', 'is_user': True},
        ),
        (
            {'text': _RENDER_TEXT},
            {'text': _RENDER_TEXT, 'speaker_id': DEFAULT_SPEAKER_ID},
        ),
        (
            {'text': _RENDER_TEXT},
            {'text': _RENDER_TEXT, 'person_id': '   '},
        ),
        (
            {'text': _RENDER_TEXT, 'is_user': False},
            {'text': _RENDER_TEXT},
        ),
        (
            {'text': '', 'speaker': 'SPEAKER_07'},
            {'text': '   ', 'speaker': 'SPEAKER_07'},
        ),
        (
            {'text': '', 'speaker': 'SPEAKER_07'},
            {'text': '', 'speaker': '  SPEAKER_07  '},
        ),
    ]
    for left, right in same_transcript_pairs:
        stored_left = _store(left)
        stored_right = _store(right)
        assert transcript_sha256([left]) == transcript_sha256([stored_left])
        assert transcript_sha256([right]) == transcript_sha256([stored_right])
        assert transcript_sha256([stored_left]) == transcript_sha256([stored_right])
        assert _render(stored_left) == _render(stored_right)

    # The reproduction itself: padded person_id is stored as 'alice' and
    # renders Alice, not Speaker 0.
    alice = _store({'text': _RENDER_TEXT, 'person_id': 'alice'})
    padded_alice = _store({'text': _RENDER_TEXT, 'person_id': ' alice '})
    assert padded_alice.person_id == 'alice'
    assert alice.person_id == 'alice'
    assert _render(alice) == _render(padded_alice) == 'Alice: approved transfer'
    assert 'Speaker 0:' not in _render(padded_alice)

    padded_slot = _store({'text': _RENDER_TEXT, 'speaker': '  SPEAKER_07  '})
    clean_slot = _store({'text': _RENDER_TEXT, 'speaker': 'SPEAKER_07'})
    assert padded_slot.speaker == 'SPEAKER_07'
    assert padded_slot.speaker_id == 7
    assert _render(padded_slot) == _render(clean_slot) == 'Speaker 7: approved transfer'

    # Contrapositive: different rendered attribution ⇒ different digest.
    distinct = [
        _store({'text': _RENDER_TEXT, 'person_id': 'alice'}),
        _store({'text': _RENDER_TEXT, 'person_id': 'bob'}),
        _store({'text': _RENDER_TEXT, 'is_user': True}),
        _store({'text': _RENDER_TEXT, 'speaker_id': 0}),
        _store({'text': _RENDER_TEXT, 'speaker_id': 7}),
        _store({'text': '', 'speaker': 'SPEAKER_07'}),
    ]
    rendered = [_render(segment) for segment in distinct]
    digests = [transcript_sha256([segment]) for segment in distinct]
    assert rendered == [
        'Alice: approved transfer',
        'Bob: approved transfer',
        'You: approved transfer',
        'Speaker 0: approved transfer',
        'Speaker 7: approved transfer',
        'Speaker 7:',
    ]
    assert len(set(rendered)) == 6
    assert len(set(digests)) == 6

    # Reviewer's reproduction: ['approved transfer'] versus that plus an
    # empty SPEAKER_07. Binding and the production renderer must both see it.
    approved = [_store({'text': _RENDER_TEXT})]
    approved_plus_empty = [
        _store({'text': _RENDER_TEXT}),
        _store({'text': '', 'speaker': 'SPEAKER_07'}),
    ]
    assert transcript_sha256(approved) == APPROVED_TRANSFER_DIGEST
    assert transcript_sha256(approved_plus_empty) == APPROVED_PLUS_EMPTY_07_DIGEST
    assert transcript_sha256(approved) != transcript_sha256(approved_plus_empty)
    assert transcript_sha256_for_binding(approved) == APPROVED_TRANSFER_DIGEST
    assert transcript_sha256_for_binding(approved_plus_empty) == APPROVED_PLUS_EMPTY_07_DIGEST
    rendered_approved = _render_transcript(approved)
    rendered_plus = _render_transcript(approved_plus_empty)
    assert rendered_approved == 'Speaker 0: approved transfer'
    assert rendered_plus == 'Speaker 0: approved transfer\n\nSpeaker 7:'
    assert rendered_approved != rendered_plus
    assert 'Speaker 7:' not in rendered_approved
    assert 'Speaker 7:' in rendered_plus


def test_from_segments_persists_canonical_segment_not_raw_request_fields() -> None:
    """from-segments must store canonical_segment, not the raw request spelling.

    red-proof: restore ``person_id=seg.person_id`` (and the rest of the inline
    TranscriptSegment construction) in routers/developer.py.
    """
    source = (Path(__file__).resolve().parents[2] / 'routers' / 'developer.py').read_text()
    assert 'stored_transcript_segment(' in source
    assert 'person_id=seg.person_id' not in source
    assert "speaker=seg.speaker or 'SPEAKER_00'" not in source
