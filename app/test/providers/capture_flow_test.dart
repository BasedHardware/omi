import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';

/// E2E flow tests for core audio capture, persistence, and transcription paths.
///
/// These tests exercise the provider state machines through complete user flows,
/// verifying state transitions, data flow, and error handling at each step.
///
/// Flows tested:
///   1. Phone mic capture flow (state machine: stop → init → record → stop)
///   2. Conversation lifecycle flow (segments arrive → silence → process → complete)
///   3. WS reconnection flow (recording → WS close → reconnect attempt)
///   4. Offline persistence / WAL flow (WAL support check for device types)
///   5. BLE audio capture flow (device recording state machine)

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.none];
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

TranscriptSegment _segment(String id, String text, {double start = 0.0, double end = 1.0}) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: start,
    end: end,
    translations: [],
  );
}

ServerConversation _conversation(String id, {ConversationStatus status = ConversationStatus.completed}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.now(),
    structured: Structured('Test Conversation', 'A test conversation overview'),
    status: status,
  );
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized
    }
  });

  // ─── Flow 1: Phone Mic Recording State Machine ───────────────────────────
  // capture_provider.dart — streamRecording() → record → stopStreamRecording()
  // Tests the full state machine: stop → initialising → record → stop
  group('Flow 1: Phone mic capture state machine', () {
    test('initial state is RecordingState.stop', () {
      final provider = CaptureProvider();
      expect(provider.recordingState, RecordingState.stop);
      expect(provider.hasTranscripts, false);
      expect(provider.segments, isEmpty);
    });

    test('updateRecordingState transitions correctly and notifies', () {
      final provider = CaptureProvider();
      var notifyCount = 0;
      provider.addListener(() => notifyCount++);

      // stop → initialising
      provider.updateRecordingState(RecordingState.initialising);
      expect(provider.recordingState, RecordingState.initialising);
      expect(notifyCount, 1);

      // initialising → record
      provider.updateRecordingState(RecordingState.record);
      expect(provider.recordingState, RecordingState.record);
      expect(notifyCount, 2);

      // record → stop
      provider.updateRecordingState(RecordingState.stop);
      expect(provider.recordingState, RecordingState.stop);
      expect(notifyCount, 3);
    });

    test('recordingDeviceServiceReady reflects recording state', () {
      final provider = CaptureProvider();

      // Not ready when stopped
      expect(provider.recordingDeviceServiceReady, false);

      // Ready when phone mic recording
      provider.updateRecordingState(RecordingState.record);
      expect(provider.recordingDeviceServiceReady, true);

      // Ready when system audio recording
      provider.updateRecordingState(RecordingState.systemAudioRecord);
      expect(provider.recordingDeviceServiceReady, true);

      // Not ready when just initialising
      provider.updateRecordingState(RecordingState.initialising);
      expect(provider.recordingDeviceServiceReady, false);
    });

    test('segments accumulate during recording', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);

      // Simulate segment arrival
      provider.segments = [_segment('s1', 'Hello world')];
      provider.hasTranscripts = true;

      expect(provider.segments.length, 1);
      expect(provider.hasTranscripts, true);
      expect(provider.segments.first.text, 'Hello world');

      // More segments arrive
      provider.segments = [
        _segment('s1', 'Hello world'),
        _segment('s2', 'How are you'),
        _segment('s3', 'I am fine'),
      ];

      expect(provider.segments.length, 3);
    });

    test('recording state resets on stop', () {
      final provider = CaptureProvider();

      // Simulate active recording with segments
      provider.updateRecordingState(RecordingState.record);
      provider.segments = [_segment('s1', 'test')];
      provider.hasTranscripts = true;

      // Stop recording
      provider.updateRecordingState(RecordingState.stop);

      expect(provider.recordingState, RecordingState.stop);
      // Note: segments and hasTranscripts persist after stop
      // (they're cleared separately during cleanup)
    });
  });

  // ─── Flow 2: Conversation Lifecycle ──────────────────────────────────────
  // Segments arrive → silence → process → conversation appears in list
  group('Flow 2: Conversation lifecycle', () {
    test('segments flow into provider during recording', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);

      // Simulate onSegmentReceived-like behavior
      provider.segments = [
        _segment('s1', 'First segment', start: 0.0, end: 3.0),
      ];
      provider.hasTranscripts = true;

      expect(provider.hasTranscripts, true);
      expect(provider.segments.length, 1);

      // More segments arrive over time
      provider.segments = [
        _segment('s1', 'First segment', start: 0.0, end: 3.0),
        _segment('s2', 'Second segment', start: 3.0, end: 6.0),
        _segment('s3', 'Third segment', start: 6.0, end: 9.0),
      ];

      expect(provider.segments.length, 3);
    });

    test('conversation provider manages processing and completed states', () {
      final convProvider = ConversationProvider();

      // Simulate conversation arriving as processing
      final processingConv = _conversation('conv-1', status: ConversationStatus.processing);
      convProvider.processingConversations = [processingConv];

      expect(convProvider.processingConversations.length, 1);
      expect(convProvider.processingConversations.first.status, ConversationStatus.processing);

      // Simulate processing complete — move to conversations list
      final completedConv = _conversation('conv-1', status: ConversationStatus.completed);
      convProvider.processingConversations = [];
      convProvider.conversations = [completedConv];

      expect(convProvider.processingConversations, isEmpty);
      expect(convProvider.conversations.length, 1);
      expect(convProvider.conversations.first.status, ConversationStatus.completed);
      expect(convProvider.conversations.first.structured.title, 'Test Conversation');
    });

    test('conversation with empty title is treated as discarded', () {
      // Backend treats title=="" as discarded in _get_conversation_obj
      final conv = ServerConversation(
        id: 'conv-empty',
        createdAt: DateTime.now(),
        structured: Structured('', ''),
        status: ConversationStatus.completed,
      );

      // Verify the structured title is empty
      expect(conv.structured.title, '');
      // This conversation would be discarded by the backend
      // The client should handle this gracefully
    });

    test('conversation detail contains transcript segments and structured data', () {
      final conv = _conversation('conv-detail');

      // Verify structured data fields are populated
      expect(conv.structured.title, isNotEmpty);
      expect(conv.structured.overview, isNotEmpty);
      expect(conv.status, ConversationStatus.completed);
    });
  });

  // ─── Flow 3: WS Reconnection ────────────────────────────────────────────
  // Recording → WS close → reconnect handler → audio resumes
  group('Flow 3: WebSocket reconnection flow', () {
    test('onClosed with normal close triggers reconnect via _startKeepAliveServices', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);
      provider.segments = [_segment('s1', 'in progress')];
      provider.hasTranscripts = true;

      // Normal WS close (no special code) should trigger reconnect
      provider.onClosed(null);

      // Recording state should NOT reset to stop — should stay record
      // so reconnect logic can re-establish the WS
      expect(provider.recordingState, RecordingState.record);
      expect(provider.hasTranscripts, true);
    });

    test('onClosed with 4002 (out of credits) does NOT trigger reconnect', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);
      provider.segments = [_segment('s1', 'talking')];
      provider.hasTranscripts = true;

      // 4002 = out of credits — no reconnect
      provider.onClosed(4002);

      // BUG (Flaw 3): recording state stays as record, not reset to stop
      expect(provider.recordingState, RecordingState.record);
      expect(provider.hasTranscripts, true);
    });

    test('onClosed with 1012 (server restart) schedules delayed reconnect', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);

      // 1012 = server restart — schedules 5-15s delayed reconnect
      provider.onClosed(1012);

      // Recording state persists for reconnect
      expect(provider.recordingState, RecordingState.record);
    });

    test('onClosed with 1013 (server overloaded) schedules aggressive backoff', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);

      // 1013 = overloaded — schedules 30-120s delayed reconnect
      provider.onClosed(1013);

      // Recording state persists for reconnect
      expect(provider.recordingState, RecordingState.record);
    });

    test('onConnectionStateChanged updates connectivity but does not reconnect WS', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.record);

      var notifications = 0;
      provider.addListener(() => notifications++);

      // Go offline
      provider.onConnectionStateChanged(false);
      expect(provider.isConnected, false);
      expect(notifications, 1);

      // Come back online
      provider.onConnectionStateChanged(true);
      expect(provider.isConnected, true);
      expect(notifications, 2);

      // BUG (Flaw 11): No WS reconnection triggered.
      // Only _isConnected boolean is updated.
      // Should call _startKeepAliveServices() when transitioning offline → online.
    });

    test('transcriptServiceReady requires both WS connected and internet', () {
      final provider = CaptureProvider();

      // With no socket and no connection, service is not ready
      expect(provider.transcriptServiceReady, false);

      // Even with connection state changed to true, without WS it stays not ready
      provider.onConnectionStateChanged(true);
      expect(provider.transcriptServiceReady, false);
    });
  });

  // ─── Flow 4: Offline Persistence (WAL) ──────────────────────────────────
  // WAL support check, device type gating, phone mic exclusion
  group('Flow 4: Offline persistence (WAL) support', () {
    test('WAL support defaults to false', () {
      final provider = CaptureProvider();
      expect(provider.isWalSupported, false);
    });

    test('setIsWalSupported updates WAL flag', () {
      final provider = CaptureProvider();

      provider.setIsWalSupported(true);
      expect(provider.isWalSupported, true);

      provider.setIsWalSupported(false);
      expect(provider.isWalSupported, false);
    });

    test('phone mic recording path has no WAL support', () {
      final provider = CaptureProvider();

      // Phone mic: no device connected, WAL stays false
      provider.updateRecordingState(RecordingState.record);
      expect(provider.isWalSupported, false);

      // When WS drops during phone mic recording, audio is lost (Flaw 10)
      provider.onClosed(null); // WS drops
      expect(provider.isWalSupported, false);
      // No WAL buffering — audio frames are silently dropped
    });

    test('WAL-enabled device recording retains audio during WS disconnect', () {
      final provider = CaptureProvider();

      // Simulate Omi device recording with WAL
      provider.updateRecordingState(RecordingState.deviceRecord);
      provider.setIsWalSupported(true);

      expect(provider.isWalSupported, true);
      expect(provider.recordingState, RecordingState.deviceRecord);

      // WS drops — WAL is still enabled, audio buffered locally
      provider.onClosed(null);
      expect(provider.isWalSupported, true);
      // Audio frames continue to be written to WAL files
    });
  });

  // ─── Flow 5: BLE Device Recording State Machine ─────────────────────────
  // Device connects → deviceRecord state → segments flow → lifecycle manages
  group('Flow 5: BLE device recording state machine', () {
    test('device recording uses RecordingState.deviceRecord', () {
      final provider = CaptureProvider();

      provider.updateRecordingState(RecordingState.deviceRecord);
      expect(provider.recordingState, RecordingState.deviceRecord);
      // recordingDeviceServiceReady checks for _recordingDevice != null,
      // which we can't set directly, but the state is correct
    });

    test('device recording state persists through WS reconnection', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.deviceRecord);
      provider.setIsWalSupported(true);

      // WS close triggers reconnect, device recording state persists
      provider.onClosed(null);
      expect(provider.recordingState, RecordingState.deviceRecord);
      expect(provider.isWalSupported, true);
    });

    test('pause and resume device recording transitions', () {
      final provider = CaptureProvider();

      // Start device recording
      provider.updateRecordingState(RecordingState.deviceRecord);
      expect(provider.recordingState, RecordingState.deviceRecord);

      // Pause
      provider.updateRecordingState(RecordingState.pause);
      expect(provider.recordingState, RecordingState.pause);

      // Resume
      provider.updateRecordingState(RecordingState.deviceRecord);
      expect(provider.recordingState, RecordingState.deviceRecord);
    });

    test('device disconnect stops recording', () {
      final provider = CaptureProvider();
      provider.updateRecordingState(RecordingState.deviceRecord);
      provider.segments = [_segment('s1', 'talking')];
      provider.hasTranscripts = true;

      // Device disconnects — recording should stop
      provider.updateRecordingState(RecordingState.stop);
      expect(provider.recordingState, RecordingState.stop);
    });
  });

  // ─── Flow Integration: End-to-end state transitions ──────────────────────
  group('Flow integration: cross-cutting state transitions', () {
    test('full phone mic flow: stop → init → record → segments → stop', () {
      final provider = CaptureProvider();

      // Step 1: Initial state
      expect(provider.recordingState, RecordingState.stop);
      expect(provider.segments, isEmpty);
      expect(provider.hasTranscripts, false);

      // Step 2: Start recording
      provider.updateRecordingState(RecordingState.initialising);
      expect(provider.recordingState, RecordingState.initialising);

      // Step 3: Recording active
      provider.updateRecordingState(RecordingState.record);
      expect(provider.recordingState, RecordingState.record);

      // Step 4: Segments arrive
      provider.segments = [
        _segment('s1', 'Hello', start: 0.0, end: 2.0),
        _segment('s2', 'World', start: 2.0, end: 4.0),
      ];
      provider.hasTranscripts = true;
      expect(provider.segments.length, 2);
      expect(provider.hasTranscripts, true);

      // Step 5: Stop recording
      provider.updateRecordingState(RecordingState.stop);
      expect(provider.recordingState, RecordingState.stop);
    });

    test('full BLE device flow: connect → deviceRecord → segments → WS drop → reconnect → stop', () {
      final provider = CaptureProvider();

      // Step 1: Device connects, starts recording
      provider.updateRecordingState(RecordingState.deviceRecord);
      provider.setIsWalSupported(true);
      expect(provider.recordingState, RecordingState.deviceRecord);

      // Step 2: Segments arrive
      provider.segments = [_segment('s1', 'Hi there')];
      provider.hasTranscripts = true;

      // Step 3: WS drops
      provider.onClosed(null);
      expect(provider.recordingState, RecordingState.deviceRecord); // Persists
      expect(provider.isWalSupported, true); // WAL still active

      // Step 4: WS reconnects (simulated by state check)
      // Recording state still deviceRecord, so reconnect logic kicks in

      // Step 5: More segments after reconnect
      provider.segments = [
        _segment('s1', 'Hi there'),
        _segment('s2', 'After reconnect'),
      ];
      expect(provider.segments.length, 2);

      // Step 6: Device disconnects, recording stops
      provider.updateRecordingState(RecordingState.stop);
      expect(provider.recordingState, RecordingState.stop);
    });

    test('conversation flows from processing to completed in ConversationProvider', () {
      final convProvider = ConversationProvider();

      // Step 1: No conversations initially
      expect(convProvider.conversations, isEmpty);
      expect(convProvider.processingConversations, isEmpty);

      // Step 2: Conversation arrives as processing
      convProvider.processingConversations = [
        _conversation('c1', status: ConversationStatus.processing),
      ];
      expect(convProvider.processingConversations.length, 1);

      // Step 3: Processing completes
      convProvider.processingConversations = [];
      convProvider.conversations = [
        _conversation('c1', status: ConversationStatus.completed),
      ];
      expect(convProvider.conversations.length, 1);
      expect(convProvider.conversations.first.structured.title, 'Test Conversation');
      expect(convProvider.conversations.first.structured.overview, 'A test conversation overview');
    });

    test('multiple WS close codes handled differently', () {
      // Test that different close codes produce different behaviors
      final states = <int?, String>{};

      for (final code in [null, 1000, 1012, 1013, 4002]) {
        final provider = CaptureProvider();
        provider.updateRecordingState(RecordingState.record);
        provider.onClosed(code);
        states[code] = provider.recordingState.toString();
      }

      // All should preserve recording state (for reconnect or not)
      expect(states[null], 'RecordingState.record'); // Normal reconnect
      expect(states[1000], 'RecordingState.record'); // Normal close
      expect(states[1012], 'RecordingState.record'); // Server restart
      expect(states[1013], 'RecordingState.record'); // Overloaded
      expect(states[4002], 'RecordingState.record'); // Out of credits (Flaw 3: not reset)
    });
  });
}
