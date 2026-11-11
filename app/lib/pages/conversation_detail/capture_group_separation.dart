import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';

enum CaptureGroupSeparationPhase { idle, separating, failed }

/// One separation at a time, with the outcome the recordings sheet shows.
///
/// Separation is sticky on the server (the recording is never regrouped), so
/// the page confirms first and reloads only after the server accepted it.
class CaptureGroupSeparationController extends ChangeNotifier {
  CaptureGroupSeparationController({Future<CaptureGroupSeparationResult> Function(String conversationId)? separate})
      : _separateOnServer = separate ?? separateConversationFromCaptureGroup;

  final Future<CaptureGroupSeparationResult> Function(String conversationId) _separateOnServer;

  CaptureGroupSeparationPhase _phase = CaptureGroupSeparationPhase.idle;
  String? _recordingId;
  bool _disposed = false;

  CaptureGroupSeparationPhase get phase => _phase;

  /// The recording the current phase is about (being separated, or the one that failed).
  String? get recordingId => _recordingId;

  bool get isBusy => _phase == CaptureGroupSeparationPhase.separating;

  /// Separates [recordingId], then runs [reload] so the detail and the list show
  /// the new membership. An `unchanged` answer (already separated elsewhere)
  /// still reloads: the local membership is stale either way.
  Future<bool> separate(String recordingId, {required Future<void> Function() reload}) async {
    if (isBusy) return false;
    _set(CaptureGroupSeparationPhase.separating, recordingId);
    final result = await _separateOnServer(recordingId);
    if (_disposed) return false;
    if (result == CaptureGroupSeparationResult.failed) {
      _set(CaptureGroupSeparationPhase.failed, recordingId);
      return false;
    }
    await reload();
    if (_disposed) return true;
    _set(CaptureGroupSeparationPhase.idle, null);
    return true;
  }

  void reset() {
    if (isBusy || _phase == CaptureGroupSeparationPhase.idle) return;
    _set(CaptureGroupSeparationPhase.idle, null);
  }

  void _set(CaptureGroupSeparationPhase phase, String? recordingId) {
    _phase = phase;
    _recordingId = recordingId;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
