import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/local_preview_admission.dart';

import '../../support/live_preview_fakes.dart';

void main() {
  late DateTime clock;
  late LocalPreviewAdmission admission;
  late List<int> sent;
  late LivePreviewController preview;

  HeldPendantFrame frame(int value) => HeldPendantFrame([value]);
  void send(HeldPendantFrame frame) => sent.add(frame.payload.single);
  void route(int value, {bool declared = true, bool warmingUp = false}) =>
      admission.routePendant(frame(value), socketDeclared: declared, journalWarmingUp: warmingUp, send: send);

  setUp(() {
    clock = DateTime.utc(2026, 10, 26);
    sent = [];
    admission = LocalPreviewAdmission(now: () => clock, onChanged: () {});
    preview = LivePreviewController(
      engine: FakeLivePreviewEngine(),
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
    );
    admission.preview = preview;
  });
  tearDown(() => preview.dispose());

  test('a socket that did not declare local preview streams every frame at once', () {
    admission.socketPublished(declared: false);
    route(1, declared: false);
    route(2, declared: false);
    expect(sent, [1, 2]);
  });

  test('refusal: held frames reach the socket in order before any newer frame', () {
    admission.socketPublished(declared: true);
    route(1);
    route(2);
    route(3);
    expect(sent, isEmpty);
    expect(admission.heldFramesForTesting, 3);
    final admitted = admission.verdict(granted: false, socketDeclared: true, send: send);
    expect(admitted, false);
    expect(sent, [1, 2, 3], reason: 'flushed by the verdict itself');
    route(4);
    expect(sent, [1, 2, 3, 4]);
    expect(admission.heldFramesForTesting, 0);
  });

  test('a grant to a socket that did not ask, or with no preview, is a refusal too', () {
    admission.socketPublished(declared: true);
    route(1);
    admission.preview = null;
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);
    expect(sent, [1]);
  });

  test('grant: the memory copy is dropped and nothing reaches the socket', () {
    admission.socketPublished(declared: true);
    route(1);
    route(2);
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), true);
    expect(admission.heldFramesForTesting, 0);
    expect(sent, isEmpty);
    expect(admission.admitted, true);
    expect(preview.phase, isNot(LivePreviewPhase.inactive));
  });

  test('overflow stops holding: flush in order, then stream', () {
    admission.socketPublished(declared: true);
    for (var i = 0; i < LocalPreviewAdmission.maxHeldFrames; i++) {
      route(i);
    }
    expect(sent, isEmpty);
    route(LocalPreviewAdmission.maxHeldFrames);
    expect(sent, List.generate(LocalPreviewAdmission.maxHeldFrames + 1, (i) => i));
    route(9999);
    expect(sent.last, 9999);
    expect(admission.heldFramesForTesting, 0);
    // A late grant after the release only admits; nothing more to drop or send.
    final before = sent.length;
    admission.verdict(granted: true, socketDeclared: true, send: send);
    expect(sent.length, before);
  });

  test('a verdict that never arrives is a refusal after the hold window', () {
    admission.socketPublished(declared: true);
    route(1);
    clock = clock.add(LocalPreviewAdmission.verdictHold);
    route(2);
    expect(sent, [1, 2]);
  });

  test('socket close or replacement drops the memory copy (the WAL keeps it)', () {
    admission.socketPublished(declared: true);
    route(1);
    admission.revoke();
    expect(admission.heldFramesForTesting, 0);
    admission.socketPublished(declared: true);
    route(2);
    admission.socketPublished(declared: false);
    expect(admission.heldFramesForTesting, 0);
    route(3, declared: false);
    expect(sent, [3]);
  });

  test('journal warm-up holds only an admitted socket; a refused one streams', () {
    admission.socketPublished(declared: true);
    admission.verdict(granted: false, socketDeclared: true, send: send);
    route(1, warmingUp: true);
    expect(sent, [1], reason: 'never on a non-admitted session');
    admission.socketPublished(declared: true);
    admission.verdict(granted: true, socketDeclared: true, send: send);
    route(2, warmingUp: true);
    expect(sent, [1]);
    expect(admission.heldFramesForTesting, 0, reason: 'warm-up keeps no memory copy');
    route(3);
    expect(sent, [1, 3]);
  });
}
