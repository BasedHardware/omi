import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/sockets.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _root = '11111111-2222-4333-8444-555555555555';
const _recording = 'cccccccc-dddd-4eee-8fff-000000000000';

Map<String, dynamic> _audioReceipt({String owner = 'alice', String channel = '0', String? session}) {
  final wire = jsonDecode(File('test/fixtures/listen_audio_custody.json').readAsStringSync()) as Map<String, dynamic>;
  final receipt = wire['receipt'] as Map<String, dynamic>;
  for (final key in ['path', 'manifest_path']) {
    receipt[key] = (receipt[key] as String).replaceFirst('/owner/', '/$owner/');
  }
  wire['channel'] = channel;
  wire.remove('client_session_id');
  wire['recording_session_id'] = session;
  return wire;
}

Map<String, dynamic> _commit({String channel = 'mono', String? session}) => {
      'type': 'capture_committed',
      'conversation_id': 'conversation',
      'capture_root': _root,
      'channel': channel,
      'clock_epoch': '2',
      'source_start': 7,
      'source_end': 8,
      if (session != null) 'recording_session_id': session,
    };

class _Gateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? currentUser;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'test-token', expirationTime: DateTime.now().add(const Duration(hours: 1)));

  @override
  Future<void> signOut() async => currentUser = null;
}

class _ReceiptListener implements ITransctiptSegmentSocketServiceListener, ListenCustodyReceiptListener {
  final receipts = <(TranscriptSegmentSocketService, String, String, String?)>[];
  Completer<void> barrier = Completer<void>();
  final closed = Completer<void>();

  @override
  void onCustodyReceipt(TranscriptSegmentSocketService socket, MessageEvent event,
      {required String owner, String? recordingSessionId}) {
    receipts.add((socket, event.eventType, owner, recordingSessionId));
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    expect(event, isA<MessageServiceStatusEvent>());
    barrier.complete();
  }

  Future<void> receive(WebSocket peer, Iterable<Map<String, dynamic>> messages) async {
    barrier = Completer<void>();
    for (final message in messages) {
      peer.add(jsonEncode(message));
    }
    peer.add(jsonEncode({'type': 'service_status', 'status': 'ready'}));
    await barrier.future;
  }

  @override
  void onClosed([int? closeCode]) {
    if (!closed.isCompleted) closed.complete();
  }

  @override
  void onConnected() {}

  @override
  void onError(Object err) => fail('Unexpected Listen error: $err');

  @override
  void onSegmentReceived(List<TranscriptSegment> segments) => fail('Unexpected transcript');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('conversation entry and reconnect bind both receipt types to the opening session', () async {
    SharedPreferences.setMockInitialValues({'uid': 'alice'});
    await SharedPreferencesUtil.init();
    Env.init(DevEnv());
    PlatformManager.initializeForLocalHarness();
    final gateway = _Gateway();
    final auth = AuthService.instance;
    AuthService.installLocalHarnessTokenGateway(gateway);

    void signIn(String uid) {
      gateway.currentUser = AuthUserSnapshot(uid: uid);
      auth.markAuthenticatedUser(uid);
      SharedPreferencesUtil().uid = uid;
    }

    signIn('alice');
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final baseUrl = 'ws://127.0.0.1:${server.port}/';
    Env.overrideApiBaseUrl(baseUrl);
    Env.armDebugJourneyCredentialTrust();
    Env.addDebugTrustedAuthority('127.0.0.1');
    addTearDown(Env.clearApiBaseUrlOverride);

    final connections = StreamController<(Uri, String?, WebSocket)>();
    final peers = StreamIterator(connections.stream);
    addTearDown(() async {
      await peers.cancel();
      await connections.close();
    });
    server.listen((request) async {
      final peer = await WebSocketTransformer.upgrade(request);
      connections.add((request.uri, request.headers.value(HttpHeaders.authorizationHeader), peer));
    });

    final pool = SocketServicePool();
    Future<TranscriptSegmentSocketService?> open(String? session) => pool.conversation(
          codec: BleAudioCodec.opus,
          sampleRate: 16000,
          language: 'en',
          clientConversationId: session,
        );

    Future<WebSocket> nextPeer(String? session) async {
      expect(await peers.moveNext(), isTrue);
      final (uri, authorization, peer) = peers.current;
      expect(uri.path, '/v4/listen');
      expect(uri.queryParameters['audio_custody'], '1');
      expect(uri.queryParameters['channels'] ?? '1', '1');
      expect(uri.queryParameters['client_conversation_id'], session);
      expect(authorization, 'Bearer test-token');
      addTearDown(peer.close);
      return peer;
    }

    final first = (await open(_recording))!;
    addTearDown(first.stop);
    final firstPeer = await nextPeer(_recording);
    expect(await open(_recording), same(first));
    final listener = _ReceiptListener();
    first.subscribe(listener, listener);

    final outgoing = StreamIterator(firstPeer);
    addTearDown(outgoing.cancel);
    expect(await outgoing.moveNext(), isTrue);
    expect(jsonDecode(outgoing.current)['type'], 'client_state');
    first.sendEvidenceFrame(WalFrame(
      payload: [1, 2, 3],
      syncKey: FrameSyncKey([1]),
      captureRoot: _root,
      sourceClockEpoch: 2,
      sourceFramePosition: 7,
    ));
    expect(await outgoing.moveNext(), isTrue);
    expect(jsonDecode(outgoing.current), {
      'type': 'capture_evidence_frame',
      'version': 1,
      'capture_root': _root,
      'clock_epoch': 2,
      'source_frame': 7,
      'byte_length': 3,
    });
    expect(await outgoing.moveNext(), isTrue);
    expect(outgoing.current, [1, 2, 3]);

    await listener.receive(firstPeer, [
      _audioReceipt(owner: 'bob'),
      _audioReceipt(channel: '1'),
      _audioReceipt(session: 'foreign-recording'),
      _commit(channel: 'mic'),
      _commit(session: 'foreign-recording'),
      _audioReceipt(),
      _commit(session: _recording),
    ]);
    expect(listener.receipts, [
      (first, 'audio_custody', 'alice', _recording),
      (first, 'capture_committed', 'alice', _recording),
    ]);

    unawaited(firstPeer.close());
    await listener.closed.future;
    first.onMessage(jsonEncode(_audioReceipt()));
    expect(listener.receipts, hasLength(2));
    final reconnected = (await open(_recording))!;
    addTearDown(reconnected.stop);
    expect(reconnected, isNot(same(first)));
    final secondPeer = await nextPeer(_recording);
    reconnected.subscribe(listener, listener);
    first.onMessage(jsonEncode(_commit())); // A queued callback from the retired socket.
    await listener.receive(secondPeer, [
      _commit(),
      _audioReceipt(session: 'server-rollover')..['client_session_id'] = _recording,
    ]);
    expect(listener.receipts.skip(2), [
      (reconnected, 'capture_committed', 'alice', _recording),
      (reconnected, 'audio_custody', 'alice', _recording),
    ]);

    gateway.currentUser = null;
    auth.handleAuthUserChanged(null);
    signIn('alice');
    await listener.receive(secondPeer, [_audioReceipt(), _commit()]);
    expect(listener.receipts, hasLength(4));

    final signedInAgain = (await open(_recording))!;
    addTearDown(signedInAgain.stop);
    expect(signedInAgain, isNot(same(reconnected)));
    final thirdPeer = await nextPeer(_recording);
    signedInAgain.subscribe(listener, listener);
    await listener.receive(thirdPeer, [_audioReceipt(), _commit()]);
    expect(listener.receipts.skip(4), [
      (signedInAgain, 'audio_custody', 'alice', _recording),
      (signedInAgain, 'capture_committed', 'alice', _recording),
    ]);

    signIn('bob');
    await listener.receive(thirdPeer, [_audioReceipt(owner: 'bob'), _commit()]);
    expect(listener.receipts, hasLength(6));

    final unidentified = (await open(null))!;
    addTearDown(unidentified.stop);
    final fourthPeer = await nextPeer(null);
    unidentified.subscribe(listener, listener);
    await listener.receive(fourthPeer, [_audioReceipt(owner: 'bob'), _commit(session: 'server-recording')]);
    expect(listener.receipts.skip(6), [
      (unidentified, 'audio_custody', 'bob', null),
      (unidentified, 'capture_committed', 'bob', null),
    ]);

    final custom = TranscriptSegmentSocketService.create(16000, BleAudioCodec.opus, 'en',
        customSttMode: true, custodyOwner: TranscriptSegmentSocketService.captureListenOwner('bob'));
    expect(custom.audioCustodyEnabled, isFalse);

    Env.overrideApiBaseUrl(baseUrl); // A custom backend does not get the fixture's credential trust.
    final untrusted = (await open('untrusted-recording'))!;
    addTearDown(untrusted.stop);
    expect(await peers.moveNext(), isTrue);
    final (uri, authorization, untrustedPeer) = peers.current;
    addTearDown(untrustedPeer.close);
    expect(uri.queryParameters, isNot(contains('audio_custody')));
    expect(authorization, isNull);
    untrusted.subscribe(listener, listener);
    await listener.receive(untrustedPeer, [_audioReceipt(owner: 'bob'), _commit()]);
    expect(listener.receipts, hasLength(8));
  });
}
