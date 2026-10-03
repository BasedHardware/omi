import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:uuid/uuid.dart';

abstract class ChatReplySpeaker {
  Future<void> beginResponse({required String messageId, bool Function()? canBegin});
  void updateStreamingResponse({required String messageId, required String fullText, required bool isFinal});
  Future<void> interruptResponse({required String messageId, required VoiceReplyPlaybackInterruptSource source});
}

class _OmiVoicePlaybackSpeaker implements ChatReplySpeaker {
  const _OmiVoicePlaybackSpeaker(this._service);

  final OmiVoicePlaybackService _service;

  @override
  Future<void> beginResponse({required String messageId, bool Function()? canBegin}) =>
      _service.beginResponse(messageId: messageId, canBegin: canBegin);

  @override
  void updateStreamingResponse({required String messageId, required String fullText, required bool isFinal}) =>
      _service.updateStreamingResponse(messageId: messageId, fullText: fullText, isFinal: isFinal);

  @override
  Future<void> interruptResponse({required String messageId, required VoiceReplyPlaybackInterruptSource source}) =>
      _service.interruptResponse(messageId: messageId, source: source);
}

class ChatReplyReadAloud {
  ChatReplyReadAloud({ChatReplySpeaker? speaker, bool Function()? isEnabled, String Function()? playbackId})
      : _speaker = speaker ?? _OmiVoicePlaybackSpeaker(OmiVoicePlaybackService.instance),
        _isEnabled = isEnabled ?? (() => SharedPreferencesUtil().readChatRepliesAloud),
        _playbackId = playbackId ?? (() => 'chat:${const Uuid().v4()}');

  static final ChatReplyReadAloud instance = ChatReplyReadAloud();

  final ChatReplySpeaker _speaker;
  final bool Function() _isEnabled;
  final String Function() _playbackId;

  bool _active = false;
  int _generation = 0;
  int _claimedGeneration = -1;
  String? _ownedPlaybackId;

  bool get active => _active;

  int get generation => _generation;

  set active(bool value) {
    _active = value;
    if (!value) {
      _generation++;
      unawaited(_cancelOwned());
    }
  }

  void newQuery() {
    _generation++;
    unawaited(_cancelOwned());
  }

  void revoke() {
    _generation++;
    unawaited(_cancelOwned());
  }

  Future<void> readFinalReply(String text, {required int generation}) async {
    if (text.trim().isEmpty) return;
    if (!_active || !_isEnabled() || generation != _generation || generation == _claimedGeneration) return;
    _claimedGeneration = generation;
    final id = _playbackId();
    _ownedPlaybackId = id;
    bool stillAuthorized() => _active && _isEnabled() && generation == _generation && _ownedPlaybackId == id;
    try {
      await _speaker.beginResponse(messageId: id, canBegin: stillAuthorized);
    } catch (_) {
      if (_ownedPlaybackId == id) _ownedPlaybackId = null;
      return;
    }
    if (!stillAuthorized()) return;
    _speaker.updateStreamingResponse(messageId: id, fullText: text, isFinal: true);
  }

  Future<void> cancel() {
    _generation++;
    return _cancelOwned();
  }

  Future<void> _cancelOwned() async {
    final id = _ownedPlaybackId;
    if (id == null) return;
    _ownedPlaybackId = null;
    await _speaker.interruptResponse(messageId: id, source: VoiceReplyPlaybackInterruptSource.none);
  }
}
