import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart' show AppLifecycleState;
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_continuity_monitor.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/pendant_frame_ledger.dart';

/// Capture continuity: a simulated pendant streams for minutes while the
/// faults that broke capture in the field are injected, and every scenario
/// checks one invariant:
///
///   every audio frame the pendant notifies to the phone ends up either
///   streamed to the live socket or persisted in the local WAL,
///
/// plus a bound on how long capture stays down after each fault.
///
/// It runs the real CaptureController, socket service, WAL and transfer
/// coordinator over scripted transports (see [CaptureReplayWorld]). The
/// single-fault guards (network handover, server close, drop mid fenced pass,
/// hung pass) live in capture_live_recovery_test.dart and count WAL frames.
/// This suite follows each frame by identity through the socket, the WAL and
/// uploads, covers what those do not (the exact 10-20 reconnect path,
/// background and foreground, the layer-2 continuity monitor), and runs every
/// fault in one ten-minute soak. On the pre-#22873 tree (#20837: a pendant
/// reconnect during an upload pass skipped capture until a cold start) it
/// loses 125 s of audio in the reconnect scenario and 320 s in the soak.
void main() {
  /// Live capture must be back this long after a fault clears.
  const resumeBound = Duration(seconds: 5);

  late Directory directory;
  late CaptureReplayWorld world;
  late SimulatedPendant pendant;
  late PendantFrameLedger ledger;
  late List<HeldTransferPass> heldPasses;

  /// Seconds the BLE link was up while capture held no pendant subscription.
  late int uncapturedLinkedSeconds;
  var expectContinuityDeclaration = false;

  /// Continuity-monitor events (layer 2), recorded against the virtual clock.
  late List<(String, Map<String, Object>)> continuityEvents;
  late CaptureContinuityMonitor continuityMonitor;

  List<Map<String, Object>> continuityDeclarations() => continuityEvents
      .where((e) => e.$1 == 'Capture Wedge Detected' && e.$2['trigger'] == CaptureContinuityMonitor.trigger)
      .map((e) => e.$2)
      .toList();

  bool deviceCaptureUp() => pendant.linked && world.deviceConnection?.openAudioSubscriptions == 1;
  bool liveCaptureUp() => deviceCaptureUp() && world.socket?.status == PureSocketStatus.connected;

  /// Streams [duration] of pendant audio in one-second steps of virtual time.
  Future<void> stream(Duration duration) async {
    for (var s = 0; s < duration.inSeconds; s++) {
      pendant.emitSecond();
      await world.elapse(const Duration(seconds: 1));
      if (pendant.linked && !deviceCaptureUp()) uncapturedLinkedSeconds++;
    }
  }

  /// Streams until live capture is up again. Returns the time it took, or null
  /// when it did not come back within [bound].
  Future<Duration?> streamUntilLive({Duration bound = resumeBound}) async {
    var waited = Duration.zero;
    while (!liveCaptureUp()) {
      if (waited >= bound) return null;
      await stream(const Duration(seconds: 1));
      waited += const Duration(seconds: 1);
    }
    return waited;
  }

  /// DeviceProvider._onDeviceConnected: the link comes up, capture learns the
  /// device and starts pendant capture, then the connect wakes a transfer pass.
  Future<void> pendantConnects({HeldTransferPass? transfer, bool notifiesWithoutListener = true}) async {
    pendant.linkUp(notifiesWithoutListener: notifiesWithoutListener);
    world.controller.updateRecordingDevice(pendant.device);
    await world.controller.streamDeviceRecording(device: pendant.device);
    await world.settle();
    transfer?.wake(WakeTrigger.deviceConnected);
    await world.settle();
  }

  /// A BLE supervision timeout: the link drops and capture loses the device.
  Future<void> pendantDrops() async {
    pendant.linkDown();
    world.controller.updateRecordingDevice(null);
    await world.settle();
  }

  Future<void> expectEveryFrameInCustody(String phase) async {
    final report = await ledger.audit();
    expect(report.emitted, isNotEmpty, reason: '$phase: the pendant streamed nothing');
    // The ledger must see both custody paths, or a broken decoder would pass.
    expect(report.streamed, isNotEmpty, reason: '$phase: no pendant frame reached the live socket');
    expect(report.persisted, isNotEmpty, reason: '$phase: no pendant frame reached the WAL');
    expect(report.lost, isEmpty, reason: '$phase: ${report.describeLost()}');
  }

  void expectResumed(Duration? took, String fault) {
    expect(took, isNotNull, reason: 'live capture did not resume within ${resumeBound.inSeconds} s after $fault');
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_continuity_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
    continuityEvents = [];
    continuityMonitor = CaptureContinuityMonitor(
      now: world.clock.now,
      track: (event, properties) => continuityEvents.add((event, properties)),
      dogfood: () => true,
      appBuild: () => 'test',
      platform: () => 'ios',
    );
    CaptureContinuityMonitor.instance = continuityMonitor;
    pendant = SimulatedPendant(world);
    ledger = PendantFrameLedger(world, pendant);
    heldPasses = [];
    uncapturedLinkedSeconds = 0;
    expectContinuityDeclaration = false;
    await pendantConnects();
    expectResumed(await streamUntilLive(), 'the first connect');
  });

  tearDown(() async {
    // Layer 2 must stay quiet whenever layer 1's invariant holds.
    if (!expectContinuityDeclaration) {
      expect(continuityDeclarations(), isEmpty, reason: 'false continuity alarm');
    }
    for (final pass in heldPasses) {
      await pass.release();
    }
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  HeldTransferPass holdTransferPasses({Duration? fencedPassTimeLimit}) {
    final pass = HeldTransferPass(fencedPassTimeLimit: fencedPassTimeLimit);
    heldPasses.add(pass);
    return pass;
  }

  test('a pendant drop and reconnect during its own upload pass resumes capture while the pass runs', () async {
    // 2026-10-20 09:32Z: a reconnect landed 45 s into the pass the previous
    // reconnect had started, and that pass never finished (an untimed BLE
    // read). On 1.0.560-563 the second connect skipped capture for 4 h 15 m.
    await pendantDrops();
    final transfer = holdTransferPasses();
    await pendantConnects(transfer: transfer);
    expect(transfer.running, true);
    await stream(const Duration(seconds: 45));
    await pendantDrops();
    await stream(const Duration(seconds: 20));
    await pendantConnects(transfer: transfer);
    expect(transfer.running, true, reason: 'the pass is still stuck in pendant storage discovery');
    final took = await streamUntilLive();
    await stream(const Duration(seconds: 120));
    await expectEveryFrameInCustody('reconnect during an upload pass');
    expectResumed(took, 'a reconnect during an upload pass');
  });

  test('background and foreground keep every frame and foreground restores live capture', () async {
    await stream(const Duration(seconds: 30));
    world.controller.onAppLifecycleChanged(AppLifecycleState.paused);
    await stream(const Duration(seconds: 30));
    world.socket!.emitClose(1001);
    await stream(const Duration(seconds: 120));
    world.controller.onAppLifecycleChanged(AppLifecycleState.resumed);
    await world.settle();
    expectResumed(await streamUntilLive(), 'foreground');
    await stream(const Duration(seconds: 30));
    await expectEveryFrameInCustody('background and foreground');
    expect(uncapturedLinkedSeconds, 0);
  });

  test('layer 2 declares a connected pendant that nothing captures within 75 s and resolves when capture returns',
      () async {
    // The 1.0.560-563 state, still reachable with #22873 in one corner: a fresh
    // link (no audio subscription carried over) that connects inside an OS
    // upload window. Capture defers its start until the window ends, and
    // firmware 3.0.21 discards audio while connected but unsubscribed.
    expectContinuityDeclaration = true;
    final transfer = holdTransferPasses(fencedPassTimeLimit: const Duration(minutes: 30));
    transfer.wake(WakeTrigger.periodic);
    await transfer.entered;
    await pendantDrops();
    await stream(const Duration(seconds: 5));
    await pendantConnects(notifiesWithoutListener: false);
    expect(deviceCaptureUp(), false);
    await stream(const Duration(seconds: 50));
    expect(continuityDeclarations(), isEmpty, reason: 'not before the 60 s threshold');
    await stream(const Duration(seconds: 25));
    expect(continuityDeclarations(), hasLength(1), reason: 'declared within 75 s');
    expect(continuityDeclarations().single['sync_fenced'], true);
    expect(continuityMonitor.dogfoodAlert.value, isNotNull, reason: 'the dogfood banner is up');
    final lost = (await ledger.audit()).lost;
    expect(lost, isNotEmpty, reason: 'this is real loss; the monitor is what makes it visible');

    await transfer.release();
    await world.settle();
    await world.controller.pendingSourceSwitch;
    expectResumed(await streamUntilLive(), 'the OS window ended');
    await stream(const Duration(seconds: 15));
    expect(continuityMonitor.dogfoodAlert.value, isNull);
    expect(
      continuityEvents.where((e) => e.$1 == 'Capture Recovery Resolved').map((e) => e.$2['trigger']),
      [CaptureContinuityMonitor.trigger],
    );
  });

  test('ten minutes with every fault in sequence: no frame lost, no capture outage past the bound', () async {
    final outages = <String, Duration?>{};
    await stream(const Duration(seconds: 60));

    world.socket!.emitError(const SocketException('Network is unreachable'));
    world.emitNetworkChange();
    await world.settle();
    outages['network change'] = await streamUntilLive();
    await stream(const Duration(seconds: 50));

    world.socket!.emitClose(1000);
    await world.settle();
    outages['server close'] = await streamUntilLive();
    await stream(const Duration(seconds: 50));

    final transfer = holdTransferPasses();
    await pendantDrops();
    await stream(const Duration(seconds: 5));
    await pendantConnects(transfer: transfer);
    await stream(const Duration(seconds: 40));
    await pendantDrops();
    await stream(const Duration(seconds: 15));
    await pendantConnects(transfer: transfer);
    outages['reconnect during upload pass'] = await streamUntilLive();
    await stream(const Duration(seconds: 50));

    world.controller.onAppLifecycleChanged(AppLifecycleState.paused);
    await stream(const Duration(seconds: 20));
    await pendantDrops();
    await stream(const Duration(seconds: 10));
    await pendantConnects(transfer: transfer);
    world.socket?.emitClose(1001);
    await stream(const Duration(seconds: 60));
    world.controller.onAppLifecycleChanged(AppLifecycleState.resumed);
    await world.settle();
    outages['foreground'] = await streamUntilLive();
    await stream(const Duration(seconds: 60));

    await transfer.release();
    await world.settle();
    await stream(const Duration(seconds: 120));

    await expectEveryFrameInCustody('ten-minute soak');
    final missed = outages.entries.where((entry) => entry.value == null).map((entry) => entry.key).toList();
    expect(missed, isEmpty, reason: 'live capture did not resume within ${resumeBound.inSeconds} s after: $missed');
    expect(uncapturedLinkedSeconds, lessThanOrEqualTo(4 * resumeBound.inSeconds),
        reason: 'seconds with a linked pendant and no capture subscription');
  });
}

/// A transfer coordinator whose pendant-storage discovery hangs until
/// released, like a pass stuck on an untimed native BLE read. Every wake
/// joins the stuck pass.
class HeldTransferPass {
  HeldTransferPass({Duration? fencedPassTimeLimit}) {
    coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () {
        if (!_entered.isCompleted) _entered.complete();
        return _hang.future;
      },
      refreshPending: () async {},
      drain: () async => const RecordingTransferDrainResult.skipped(),
      autoUploadEnabled: () => true,
      fencedPassTimeLimit: fencedPassTimeLimit ?? RecordingTransferCoordinator.defaultFencedPassTimeLimit,
      onPassTimedOut: (trigger, _) => timedOut.add(trigger),
      scheduleCooldown: (_, __) {},
    );
  }

  late final RecordingTransferCoordinator coordinator;
  final Completer<void> _entered = Completer<void>();
  final Completer<void> _hang = Completer<void>();
  final List<Future<void>> _wakes = [];
  final List<WakeTrigger> timedOut = [];

  Future<void> get entered => _entered.future;
  bool get running => coordinator.hasInFlight;

  /// Completes once every wake has returned (released, or ended by a time limit).
  Future<void> get wakesSettled => Future.wait(_wakes);

  void wake(WakeTrigger trigger) => _wakes.add(coordinator.wake(trigger));

  Future<void> release() async {
    if (_hang.isCompleted) return;
    _hang.complete();
    await wakesSettled;
    coordinator.dispose();
  }
}
