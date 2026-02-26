import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/utils/logger.dart';

class WatchAskQuestionService {
  static const _channel = MethodChannel('com.omi/watch_questions');
  static final WatchAskQuestionService _instance = WatchAskQuestionService._();

  factory WatchAskQuestionService() => _instance;

  WatchAskQuestionService._();

  bool _initialized = false;

  void initialize() {
    if (_initialized) return;
    _initialized = true;

    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onAskQuestion') {
        final args = call.arguments as Map<dynamic, dynamic>;
        final filePath = args['filePath'] as String;
        final sampleRate = (args['sampleRate'] as num).toDouble();
        _handleAskQuestion(filePath, sampleRate);
      }
    });
  }

  Future<void> _handleAskQuestion(String pcmFilePath, double sampleRate) async {
    final pcmFile = File(pcmFilePath);
    File? wavFile;
    try {
      if (!await pcmFile.exists()) {
        Logger.error('Ask question PCM file not found: $pcmFilePath');
        return;
      }

      final pcmData = await pcmFile.readAsBytes();
      wavFile = await _pcmToWav(pcmData, sampleRate.toInt());

      String answer = '';
      await for (var chunk in sendVoiceMessageStreamServer([wavFile])) {
        if (chunk.type == MessageChunkType.data) {
          answer += chunk.text;
        } else if (chunk.type == MessageChunkType.done && chunk.message != null) {
          answer = chunk.message!.text;
        }
      }

      if (answer.isNotEmpty) {
        await _sendNotification('Omi', answer);
      }
    } catch (e) {
      Logger.error('Failed to handle ask question: $e');
    } finally {
      try {
        await pcmFile.delete();
      } catch (_) {}
      try {
        if (wavFile != null) await wavFile.delete();
      } catch (_) {}
    }
  }

  Future<File> _pcmToWav(Uint8List pcmData, int sampleRate) async {
    const channels = 1;
    const bitsPerSample = 16;
    final byteRate = sampleRate * channels * bitsPerSample ~/ 8;
    final blockAlign = channels * bitsPerSample ~/ 8;
    final dataSize = pcmData.length;
    final fileSize = 36 + dataSize;

    final header = ByteData(44);
    // RIFF header
    header.setUint8(0, 0x52); // R
    header.setUint8(1, 0x49); // I
    header.setUint8(2, 0x46); // F
    header.setUint8(3, 0x46); // F
    header.setUint32(4, fileSize, Endian.little);
    header.setUint8(8, 0x57); // W
    header.setUint8(9, 0x41); // A
    header.setUint8(10, 0x56); // V
    header.setUint8(11, 0x45); // E
    // fmt chunk
    header.setUint8(12, 0x66); // f
    header.setUint8(13, 0x6D); // m
    header.setUint8(14, 0x74); // t
    header.setUint8(15, 0x20); // (space)
    header.setUint32(16, 16, Endian.little); // chunk size
    header.setUint16(20, 1, Endian.little); // PCM format
    header.setUint16(22, channels, Endian.little);
    header.setUint32(24, sampleRate, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, blockAlign, Endian.little);
    header.setUint16(34, bitsPerSample, Endian.little);
    // data chunk
    header.setUint8(36, 0x64); // d
    header.setUint8(37, 0x61); // a
    header.setUint8(38, 0x74); // t
    header.setUint8(39, 0x61); // a
    header.setUint32(40, dataSize, Endian.little);

    final wavPath = '${DateTime.now().millisecondsSinceEpoch}_ask_question.wav';
    final tempDir = Directory.systemTemp;
    final wavFile = File('${tempDir.path}/$wavPath');
    await wavFile.writeAsBytes([...header.buffer.asUint8List(), ...pcmData]);
    return wavFile;
  }

  Future<void> _sendNotification(String title, String body) async {
    final plugin = FlutterLocalNotificationsPlugin();
    const androidDetails = AndroidNotificationDetails(
      'omi_ask_question',
      'Omi Questions',
      channelDescription: 'Answers to questions asked via Apple Watch',
      importance: Importance.high,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails();
    const details = NotificationDetails(android: androidDetails, iOS: iosDetails);
    await plugin.show(DateTime.now().millisecondsSinceEpoch ~/ 1000, title, body, details);
  }
}
