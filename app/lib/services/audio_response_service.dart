import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/openai.dart';
import 'package:omi/backend/preferences.dart';

class AudioResponseService {
  static final AudioResponseService _instance = AudioResponseService._internal();
  factory AudioResponseService() => _instance;
  AudioResponseService._internal();

  static const MethodChannel _channel = MethodChannel('com.omi.audio_response');

  /// Check if headphones are currently connected
  Future<bool> isHeadphonesConnected() async {
    if (!Platform.isIOS) return false;
    
    try {
      final result = await _channel.invokeMethod('isHeadphonesConnected');
      return result == true;
    } catch (e) {
      print('[AudioResponseService] Error checking headphones: $e');
      return false;
    }
  }

  /// Play text as speech through headphones using OpenAI TTS (iOS only)
  /// Only plays if headphones are connected and user has enabled the feature
  Future<bool> playTextToSpeech(String text) async {
    final pipelineStart = DateTime.now();
    print('[AudioResponseService] ⏱️ PIPELINE START - text length: ${text.length}');
    
    if (!Platform.isIOS) {
      print('[AudioResponseService] Not iOS platform, skipping');
      return false;
    }
    
    // Check user preference
    if (!SharedPreferencesUtil().playAudioResponseInHeadphones) {
      print('[AudioResponseService] Audio response in headphones is disabled in settings');
      return false;
    }

    if (text.isEmpty) {
      print('[AudioResponseService] Text is empty, skipping');
      return false;
    }

    try {
      // Generate speech using OpenAI TTS
      final ttsStart = DateTime.now();
      final audioBytes = await openAiTextToSpeech(text, voice: 'nova', model: 'tts-1');
      final ttsDuration = DateTime.now().difference(ttsStart).inMilliseconds;
      print('[AudioResponseService] ⏱️ TTS generation took ${ttsDuration}ms');
      
      if (audioBytes == null || audioBytes.isEmpty) {
        print('[AudioResponseService] Failed to generate audio from OpenAI');
        return false;
      }

      print('[AudioResponseService] Received ${audioBytes.length} bytes, sending to iOS...');
      
      // Send audio bytes to iOS for playback
      final transferStart = DateTime.now();
      final bool? result = await _channel.invokeMethod('playAudioBytes', {
        'audioData': audioBytes,
      });
      final playbackCompleteDuration = DateTime.now().difference(transferStart).inMilliseconds;
      
      final totalDuration = DateTime.now().difference(pipelineStart).inMilliseconds;
      
      // The method channel returns after playback completes, so we can estimate transfer time
      // Assuming ~50ms for actual data transfer, the rest is playback time
      final estimatedTransferTime = 50; // ms
      final estimatedPlaybackTime = playbackCompleteDuration - estimatedTransferTime;
      
      print('[AudioResponseService] ⏱️ iOS transfer: ~${estimatedTransferTime}ms, Playback: ~${estimatedPlaybackTime}ms');
      print('[AudioResponseService] ⏱️ TOTAL TIME: ${totalDuration}ms (TTS: ${ttsDuration}ms, Transfer+Playback: ${playbackCompleteDuration}ms)');
      print('[AudioResponseService] ⏱️ TIME TO FIRST AUDIO: ${ttsDuration + estimatedTransferTime}ms (what user waits)');
      print('[AudioResponseService] iOS playback result: $result');
      return result ?? false;
    } on PlatformException catch (e) {
      print('[AudioResponseService] PlatformException: ${e.message}');
      return false;
    } catch (e) {
      print('[AudioResponseService] Exception: $e');
      return false;
    }
  }

  /// Stop current audio playback
  Future<void> stopPlayback() async {
    if (!Platform.isIOS) return;
    
    try {
      await _channel.invokeMethod('stopPlayback');
    } catch (e) {
      print('[AudioResponseService] Error stopping playback: $e');
    }
  }

  /// Activate audio session for background playback
  /// Call this when app starts or when BLE connects to enable background TTS
  Future<void> activateAudioSession() async {
    if (!Platform.isIOS) return;
    
    try {
      await _channel.invokeMethod('activateAudioSession');
      print('[AudioResponseService] ✅ Audio session activated for background playback');
    } catch (e) {
      print('[AudioResponseService] Error activating audio session: $e');
    }
  }
}

