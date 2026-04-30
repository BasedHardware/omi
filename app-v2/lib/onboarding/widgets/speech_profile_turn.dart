import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/services/audio_sources/phone_mic_source.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Phase 1 speech-profile turn.
///
/// Records ~5 seconds of PCM16 16 kHz mono audio from the phone mic, pipes the
/// raw bytes through [PhoneMicSource] to confirm 320-byte frames flow, then
/// reports back to the chat. STT / upload / diarization all arrive in later
/// phases — this just proves the audio pipeline matches desktop-v2's PCM16
/// capture format end-to-end.
class SpeechProfileTurn extends StatefulWidget {
  final String turnId;
  const SpeechProfileTurn({super.key, required this.turnId});

  @override
  State<SpeechProfileTurn> createState() => _SpeechProfileTurnState();
}

class _SpeechProfileTurnState extends State<SpeechProfileTurn> {
  static const Duration _captureDuration = Duration(seconds: 5);
  static const int _sampleRate = 16000;

  FlutterSoundRecorder? _recorder;
  StreamSubscription<Uint8List>? _audioSub;
  StreamController<Uint8List>? _audioStream;
  PhoneMicSource? _source;
  Timer? _stopTimer;
  Timer? _tick;

  bool _busy = false;
  bool _recording = false;
  bool _captured = false;
  int _frameCount = 0;
  double _progress = 0;
  String? _error;

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      setState(() {
        _busy = false;
        _error = 'Microphone permission required';
      });
      return;
    }

    _recorder = FlutterSoundRecorder();
    await _recorder!.openRecorder();

    _source = PhoneMicSource();
    _audioStream = StreamController<Uint8List>();
    _audioSub = _audioStream!.stream.listen((chunk) {
      final frames = _source!.processBytes(chunk);
      _frameCount += frames.length;
    });

    final start = DateTime.now();
    _tick = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (!mounted) return;
      final elapsed = DateTime.now().difference(start).inMilliseconds;
      setState(() => _progress = (elapsed / _captureDuration.inMilliseconds).clamp(0, 1).toDouble());
    });

    await _recorder!.startRecorder(
      toStream: _audioStream!.sink,
      codec: Codec.pcm16,
      numChannels: 1,
      sampleRate: _sampleRate,
      bufferSize: PhoneMicSource.frameSize * 2,
    );

    setState(() {
      _busy = false;
      _recording = true;
    });

    _stopTimer = Timer(_captureDuration, _finish);
  }

  Future<void> _finish() async {
    _tick?.cancel();
    await _recorder?.stopRecorder();
    final remaining = _source?.flush() ?? [];
    _frameCount += remaining.length;
    await _audioSub?.cancel();
    await _audioStream?.close();
    await _recorder?.closeRecorder();

    if (!mounted) return;
    setState(() {
      _recording = false;
      _captured = _frameCount > 0;
      _progress = 1;
    });

    debugPrint('[SpeechProfileTurn] Captured $_frameCount PCM16 frames @ 16kHz mono (320B each)');

    if (mounted) {
      await context.read<OnboardingChatProvider>().reportWidgetCapture(context, widget.turnId, true);
    }
  }

  void _skip() {
    context.read<OnboardingChatProvider>().skipCurrent(context);
  }

  @override
  void dispose() {
    _tick?.cancel();
    _stopTimer?.cancel();
    _audioSub?.cancel();
    _audioStream?.close();
    _recorder?.closeRecorder();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      padding: const EdgeInsets.all(AppStyles.spacingL),
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l.onboardingSpeechCardTitle,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary)),
          const SizedBox(height: 6),
          Text(l.onboardingSpeechCardBody,
              style: const TextStyle(fontSize: 13, color: AppColors.textTertiary, height: 1.4)),
          const SizedBox(height: AppStyles.spacingL),
          Container(
            padding: const EdgeInsets.all(AppStyles.spacingL),
            decoration: BoxDecoration(
              color: AppColors.backgroundTertiary,
              borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              border: Border.all(color: AppColors.brandAccent.withValues(alpha: 0.30)),
            ),
            child: Text(
              '"${l.onboardingSpeechCardSample}"',
              style: const TextStyle(fontSize: 14, fontStyle: FontStyle.italic, color: AppColors.textSecondary),
            ),
          ),
          const SizedBox(height: AppStyles.spacingL),
          if (_recording) ...[
            LinearProgressIndicator(
              value: _progress,
              backgroundColor: AppColors.backgroundTertiary,
              valueColor: const AlwaysStoppedAnimation(AppColors.brandPrimary),
              minHeight: 4,
            ),
            const SizedBox(height: 8),
            Text(l.onboardingSpeechRecording,
                style: const TextStyle(fontSize: 13, color: AppColors.brandPrimary, fontWeight: FontWeight.w500)),
          ] else if (_captured) ...[
            Row(
              children: [
                const Icon(Icons.check_circle, color: AppColors.successColor, size: 20),
                const SizedBox(width: 8),
                Text(l.onboardingSpeechCaptured,
                    style: const TextStyle(fontSize: 14, color: AppColors.successColor, fontWeight: FontWeight.w600)),
                const SizedBox(width: 8),
                Text('($_frameCount frames)',
                    style: const TextStyle(fontSize: 12, color: AppColors.textTertiary)),
              ],
            ),
          ] else ...[
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _busy ? null : _start,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.brandPrimary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusPill)),
                    ),
                    child: Text(_busy ? '…' : 'Start'),
                  ),
                ),
                const SizedBox(width: 12),
                TextButton(
                  onPressed: _skip,
                  child: Text(l.onboardingSpeechSkip,
                      style: const TextStyle(color: AppColors.textTertiary, fontWeight: FontWeight.w500)),
                ),
              ],
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: AppColors.errorColor, fontSize: 13)),
          ],
        ],
      ),
    );
  }
}
