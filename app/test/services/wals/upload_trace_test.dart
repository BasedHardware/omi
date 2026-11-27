import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/upload_trace.dart';

void main() {
  test('takes the bounded hold label with the matching request trace', () {
    final trace = UploadTrace(now: () => DateTime.fromMillisecondsSinceEpoch(2000000));
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'a', sealedAtSeconds: 1990, holdState: 'bg300');
    expect(trace.take('/b.bin'), isNull);
    expect(trace.take('/a.bin')?.holdState, 'bg300');
    expect(trace.take('/a.bin'), isNull);
  });

  late DateTime clock;
  late UploadTrace trace;

  DateTime at(int seconds) => DateTime.fromMillisecondsSinceEpoch(seconds * 1000, isUtc: true);

  setUp(() {
    clock = at(2000);
    trace = UploadTrace(now: () => clock);
  });

  test('hold age includes time before dispatch and is recalculated on replay', () {
    trace.prepare(
      firstFilePath: '/a.bin',
      oldestId: 'w1',
      sealedAtSeconds: 1990,
      holdState: 'bg300',
      holdSealedAtMs: 1990123,
    );
    final upload = trace.take('/a.bin');
    clock = at(3190);
    expect(trace.holdHeadersAtSend(upload, holdEnabled: true), {
      'X-Omi-Upload-Hold': 'bg300',
      'X-Omi-Upload-Hold-Age-Ms': '1199877',
    });
    clock = at(3210);
    expect(trace.holdHeadersAtSend(upload, holdEnabled: true)['X-Omi-Upload-Hold-Age-Ms'], '1219877');
    expect(trace.holdHeadersAtSend(upload, holdEnabled: false), {'X-Omi-Upload-Hold': 'none'});
  });

  test('recovered uploads keep their marker across retries and flag-off', () {
    trace.prepare(
      firstFilePath: '/recovered.bin',
      oldestId: 'recovered',
      sealedAtSeconds: 1990,
      holdState: 'fg60',
      holdSealedAtMs: 1990000,
      recovered: true,
      journalRecovery: WalJournalRecovery.recovered,
    );
    final upload = trace.take('/recovered.bin');
    expect(trace.holdHeadersAtSend(upload, holdEnabled: true), {
      'X-Omi-Upload-Hold': 'fg60',
      'X-Omi-Upload-Hold-Age-Ms': '10000',
      'X-Omi-Upload-Recovered': '1',
      'X-Omi-Upload-Journal-Recovery': 'recovered',
    });
    expect(trace.holdHeadersAtSend(upload, holdEnabled: false), {
      'X-Omi-Upload-Hold': 'none',
      'X-Omi-Upload-Recovered': '1',
    });
  });

  test('journal evidence and reported label stay independent at send', () {
    trace.prepare(
      firstFilePath: '/a.bin',
      oldestId: 'w1',
      sealedAtSeconds: 1990,
      holdState: 'fg60',
      journalRecovery: WalJournalRecovery.recovered,
    );
    final upload = trace.take('/a.bin');
    expect(trace.holdHeadersAtSend(upload, holdEnabled: true), {
      'X-Omi-Upload-Hold': 'fg60',
      'X-Omi-Upload-Recovered': '0',
      'X-Omi-Upload-Journal-Recovery': 'recovered',
    });
    expect(trace.holdHeadersAtSend(upload, holdEnabled: false), {'X-Omi-Upload-Hold': 'none'});
  });

  test('hold age clamps clock changes and requires a held file', () {
    const UploadTraceSnapshot held = (
      trace: 'trace',
      holdState: 'fg60',
      holdSealedAtMs: 2010000,
      recovered: false,
      journalRecovery: null,
    );
    expect(trace.holdHeadersAtSend(held, holdEnabled: true)['X-Omi-Upload-Hold-Age-Ms'], '0');
    clock = at(200000);
    expect(trace.holdHeadersAtSend(held, holdEnabled: true)['X-Omi-Upload-Hold-Age-Ms'], '86400000');
    const UploadTraceSnapshot unheld = (
      trace: 'trace',
      holdState: 'none',
      holdSealedAtMs: 2010000,
      recovered: false,
      journalRecovery: null,
    );
    expect(trace.holdHeadersAtSend(unheld, holdEnabled: true), {'X-Omi-Upload-Hold': 'none'});
  });

  test('a first attempt with no gate reports none and one attempt', () {
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    expect(trace.take('/a.bin')?.trace, 'sealed=1990;first=2000;gate=none;attempts=1');
    expect(trace.take('/a.bin'), isNull, reason: 'taken once');
  });

  test('a gate that closed after the seal is named; later attempts keep the first attempt time', () {
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    trace.take('/a.bin');
    clock = at(2600);
    trace.noteGate('rate_limited');
    clock = at(4000);
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    expect(trace.take('/a.bin')?.trace, 'sealed=1990;first=2000;gate=rate_limited;attempts=2');
  });

  test('a gate from before the file was sealed did not hold it', () {
    clock = at(1000);
    trace.noteGate('background');
    clock = at(2000);
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    expect(trace.take('/a.bin')?.trace, contains('gate=none'));
  });

  test('unknown labels are folded into other; a missing seal time sends nothing', () {
    clock = at(2100);
    trace.noteGate('something new');
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    expect(trace.take('/a.bin')?.trace, contains('gate=other'));
    trace.prepare(firstFilePath: '/b.bin', oldestId: 'w2', sealedAtSeconds: 0);
    expect(trace.take('/b.bin'), isNull);
  });

  test('an accepted upload starts a fresh count for that file', () {
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    trace.take('/a.bin');
    trace.accepted('w1');
    clock = at(3000);
    trace.prepare(firstFilePath: '/a.bin', oldestId: 'w1', sealedAtSeconds: 1990);
    expect(trace.take('/a.bin')?.trace, 'sealed=1990;first=3000;gate=none;attempts=1');
  });

  test('memory stays bounded', () {
    for (var i = 0; i < 2000; i++) {
      trace.prepare(firstFilePath: '/f$i.bin', oldestId: 'w$i', sealedAtSeconds: 1990);
    }
    expect(trace.take('/f0.bin'), isNull, reason: 'oldest parked headers were dropped');
    expect(trace.take('/f1999.bin'), isNotNull);
  });

  test('every label the phone can send is one the server accepts', () {
    expect(UploadTrace.gates, {
      'none',
      'rate_limited',
      'auto_upload_off',
      'background',
      'retries_exhausted',
      'in_flight',
      'offline',
      'server_hold',
      'other',
    });
  });
}
