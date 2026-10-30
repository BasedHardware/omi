import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/ui/format/omi_date_format.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));

OmiDateFormat _dates({bool clock24 = true}) =>
    OmiDateFormat(locale: const Locale('en'), use24HourFormat: clock24, l10n: _l10n);

TranscriptSegment _line(double start, double end) => TranscriptSegment(
      id: 's$start',
      text: 'hello',
      speaker: 'SPEAKER_0',
      isUser: true,
      personId: null,
      start: start,
      end: end,
      translations: [],
    );

/// A dictation captured inside a long streaming session: started_at is the session's origin, so
/// finished_at - started_at over-counts (#4056); the length shown anywhere is the speech span.
ServerConversation _call({
  String title = 'Health updates and smart home renovation',
  DateTime? start,
  List<TranscriptSegment>? lines,
}) {
  final at = start ?? DateTime(2026, 10, 22, 8, 31);
  return ServerConversation(
    id: '1339',
    createdAt: at,
    startedAt: at,
    finishedAt: at.add(const Duration(hours: 3)),
    structured: Structured(title, ''),
    transcriptSegments: lines ?? [_line(0, 30), _line(30, 840)],
  );
}

void main() {
  setUpAll(() => initializeDateFormatting('en'));

  group('The transcript document', () {
    test('carries the title, when it started, the length the page shows, and every line', () {
      const lines = '[00:01] Jannet D: Ну сейчас у него 142 килограмма.\n\n'
          '[00:04] Roman: Да кошмар, я вообще не понимаю.';
      final doc = conversationTranscriptDocument(_call(), dates: _dates(), l10n: _l10n, transcript: lines);
      final head = doc.split('\n');
      expect(head[0], 'Health updates and smart home renovation');
      expect(head[1], 'Oct 22, 2026 08:31 · 14m',
          reason: 'the speech span, as on the detail page, not the 3h session window');
      expect(doc, contains(lines), reason: 'the full text, not a link');
      expect(doc.endsWith('\n'), isTrue);
    });

    test("follows the reader's clock setting", () {
      final doc = conversationTranscriptDocument(_call(), dates: _dates(clock24: false), l10n: _l10n, transcript: 'x');
      expect(doc.split('\n')[1], matches(RegExp(r'^Oct 22, 2026,? 8:31\sAM · 14m$')));
    });

    test('omits a length when there is none to measure', () {
      final unmeasured = ServerConversation(
        id: 'x',
        createdAt: DateTime(2026, 10, 22, 8, 31),
        startedAt: DateTime(2026, 10, 22, 8, 31),
        structured: Structured('Untimed', ''),
      );
      final doc = conversationTranscriptDocument(unmeasured, dates: _dates(), l10n: _l10n, transcript: '');
      expect(doc.split('\n')[1], 'Oct 22, 2026 08:31');
    });
  });

  group('The file name', () {
    test('is the start stamp and the title', () {
      expect(conversationTranscriptFileName(_call()), '2026-10-22 0831 Health updates and smart home renovation.txt');
      expect(conversationTranscriptFileName(_call(start: DateTime(2026, 3, 5, 14, 5))), startsWith('2026-03-05 1405 '),
          reason: 'a 24-hour, zero-padded stamp sorts by date');
      expect(conversationTranscriptFileName(_call(title: '')), '2026-10-22 0831.txt');
    });

    test('drops every character a file system refuses', () {
      final name = conversationTranscriptFileName(_call(title: 'a/b\\c: d? "e" <f> |g| *h*\ti\nj\u0007k'));
      expect(name, '2026-10-22 0831 a b c d e f g h i j k.txt');
    });

    test('never splits a grapheme', () {
      // 15-byte stamp, a space and 157 letters leave 3 bytes before ".txt" reaches 180: a cut by
      // code units would keep half of the 4-byte emoji; a cut by graphemes leaves it out whole.
      final name = conversationTranscriptFileName(_call(title: '${'a' * 157}😀'));
      expect(name, '2026-10-22 0831 ${'a' * 157}.txt');
    });

    test('stays within the 255-byte limit Android imposes, whatever the script', () {
      // One Devanagari grapheme is several code points of 3 bytes each: 60 characters reached 281
      // bytes, past what ext4 and f2fs accept.
      final hindi = 'स्वास्थ्य अपडेट और स्मार्ट होम नवीनीकरण के बारे में लंबी बातचीत ' * 3;
      final name = conversationTranscriptFileName(_call(title: hindi));
      expect(utf8.encode(name).length, lessThanOrEqualTo(180));
      expect(name, startsWith('2026-10-22 0831 स्वास्थ्य'));
      expect(name.endsWith('.txt'), isTrue);
    });
  });

  group('Writing the export', () {
    late Directory temp;
    setUp(() async => temp = await Directory.systemTemp.createTemp('transcript-export-'));
    tearDown(() async => temp.delete(recursive: true));

    test('writes the document into a folder of its own', () async {
      final file = await writeConversationTranscript(_call(), dates: _dates(), l10n: _l10n, temporaryDirectory: temp);
      expect(file.parent.path, '${temp.path}/transcript_exports');
      expect(file.path.split('/').last, '2026-10-22 0831 Health updates and smart home renovation.txt');
      expect(await file.readAsString(), startsWith('Health updates and smart home renovation\n'));
    });

    test('sweeps exports older than a day, keeps recent ones', () async {
      final folder = await Directory('${temp.path}/transcript_exports').create();
      final old = File('${folder.path}/old.txt')..writeAsStringSync('x');
      final recent = File('${folder.path}/recent.txt')..writeAsStringSync('y');
      final now = DateTime.now();
      old.setLastModifiedSync(now.subtract(const Duration(days: 2)));
      recent.setLastModifiedSync(now.subtract(const Duration(hours: 2)));

      await writeConversationTranscript(_call(), dates: _dates(), l10n: _l10n, temporaryDirectory: temp, now: now);

      expect(old.existsSync(), isFalse, reason: 'a private transcript left in plain text');
      expect(recent.existsSync(), isTrue, reason: 'a receiving app may still be reading it');
    });

    test('an old export that cannot be removed does not stop the sweep', () async {
      final folder = await Directory('${temp.path}/transcript_exports').create();
      final now = DateTime.now();
      final stale = <File>[];
      for (final name in ['a.txt', 'b.txt']) {
        final f = File('${folder.path}/$name')..writeAsStringSync('x');
        f.setLastModifiedSync(now.subtract(const Duration(days: 2)));
        stale.add(f);
      }
      // The first delete fails, as it does for a file the receiving app still holds open.
      await sweepTranscriptExports(folder, now.subtract(const Duration(days: 1)), delete: (f) async {
        if (f.path.endsWith('a.txt')) throw FileSystemException('busy', f.path);
        await f.delete();
      });
      expect(stale[0].existsSync(), isTrue);
      expect(stale[1].existsSync(), isFalse, reason: 'one stuck file must not stop the rest');
    });

    test('a write that fails throws to the caller', () async {
      final notADirectory = File('${temp.path}/blocked')..writeAsStringSync('');
      expect(
        () => writeConversationTranscript(_call(),
            dates: _dates(), l10n: _l10n, temporaryDirectory: Directory(notADirectory.path)),
        throwsA(isA<FileSystemException>()),
      );
    });
  });
}
