import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/transcript_hash.dart';

TranscriptSegment _seg(
  String text, {
  String speaker = 'SPEAKER_00',
  bool isUser = false,
  String? personId,
  String id = 's',
}) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: speaker,
    isUser: isUser,
    personId: personId,
    start: 0,
    end: 1,
    translations: const [],
  );
}

void main() {
  test('encoding version is v5', () {
    expect(transcriptHashEncodingVersion, 5);
  });

  test('known-answer vector pins Alice/Bob to the Python digest', () {
    const digest = '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40';
    expect(
      transcriptSha256FromMaps([
        {'speaker': 'Alice', 'text': 'I agree'},
        {'speaker': 'Bob', 'text': 'I refuse'},
      ]),
      digest,
    );
    expect(
      transcriptSha256([_seg('I agree', speaker: 'Alice'), _seg('I refuse', speaker: 'Bob')]),
      digest,
    );
  });

  test('empty list hashes the empty byte string', () {
    expect(transcriptSha256FromMaps([]), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(
      transcriptSha256FromMaps([
        {'text': ''},
      ]),
      '1f4edaaa8c0b550ed42040ed654a8bccfd34e121da991f1b986f9821e3d360a8',
    );
    expect(
      transcriptSha256FromMaps([
        {'text': ''},
      ]),
      isNot('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    );
  });

  test('hello/world and unicode match the Python fixtures', () {
    expect(
      transcriptSha256FromMaps([
        {'text': 'hello'},
        {'text': 'world'},
      ]),
      '8c07ee1d1a21bd1f1f319362b1435d6e875f8e24ef326dc08ecf113e226e3410',
    );
    expect(
      transcriptSha256FromMaps([
        {'text': 'café 你好'},
      ]),
      'de349219ac8122fb4f1bd000167d933ed6657dff1ad3835e1deb06a2bf79eef5',
    );
  });

  test('attribution and speaker_id change the digest', () {
    expect(
      transcriptSha256FromMaps([
        {'text': 'I approved the transfer', 'is_user': true},
      ]),
      '51d7fb6fb4e3cf863a1210d21280cbfb91e8dd16d818d9d6208af00470a5e3c9',
    );
    expect(
      transcriptSha256FromMaps([
        {'text': 'I approved the transfer', 'person_id': 'alice'},
      ]),
      '55629d482ae03ac3ca5f315ff39a6ac156e1ada4e4f6428b2a6fb9ec88b36a8d',
    );
    expect(
      transcriptSha256FromMaps([
        {'text': 'I approved the transfer', 'speaker_id': 0},
      ]),
      '863cf7938e692d22b06f5b757ad5330a517c87f60d115e5dd97a973fbc248d50',
    );
    expect(
      transcriptSha256FromMaps([
        {'text': 'I approved the transfer', 'speaker_id': 7},
      ]),
      'd7dfcd646cda9e7d068693db981c82e11d144d376c800ba0640b611d3768ecdf',
    );
  });

  test('SPEAKER_07 without speaker_id derives 7', () {
    expect(
      transcriptSha256FromMaps([
        {'speaker': 'SPEAKER_07', 'text': 'hello'},
      ]),
      transcriptSha256([_seg('hello', speaker: 'SPEAKER_07')]),
    );
  });

  test('padded speaker and text strip to the same digest', () {
    expect(
      transcriptSha256FromMaps([
        {'speaker': '  SPEAKER_07  ', 'text': '  hello  '},
      ]),
      transcriptSha256FromMaps([
        {'speaker': 'SPEAKER_07', 'text': 'hello'},
      ]),
    );
  });

  test('swapped attribution is a different digest', () {
    const original = '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40';
    expect(
      transcriptSha256FromMaps([
        {'speaker': 'Bob', 'text': 'I agree'},
        {'speaker': 'Alice', 'text': 'I refuse'},
      ]),
      isNot(original),
    );
  });
}
