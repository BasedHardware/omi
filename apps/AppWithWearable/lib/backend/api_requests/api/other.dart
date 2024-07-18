import 'dart:convert';
import 'dart:io';

import 'package:deepgram_speech_to_text/deepgram_speech_to_text.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<List<TranscriptSegment>> deepgramTranscribe(File file) async {
  debugPrint('deepgramTranscribe');
  var startTime = DateTime.now();
  // TODO: why there seems to be no punctuation
  Deepgram deepgram = Deepgram(getDeepgramApiKeyForUsage(), baseQueryParams: {
    'model': 'nova-2-general',
    'detect_language': false,
    'language': SharedPreferencesUtil().recordingsLanguage,
    'filler_words': false,
    'punctuate': true,
    'diarize': true,
    'smart_format': true,
    'multichannel': false
    // 'detect_topics': true,
    // 'topics': true,
    // 'intents': true,
    // 'sentiment': true,
    // TODO: try more options, sentiment analysis, intent, topics
  });

  DeepgramSttResult res = await deepgram.transcribeFromFile(file);
  debugPrint('Deepgram took: ${DateTime.now().difference(startTime).inSeconds} seconds');
  var data = jsonDecode(res.json);
  // debugPrint('Response body: ${res.json}');
  var result = data['results']['channels'][0]['alternatives'][0];
  List<TranscriptSegment> segments = [];
  for (var word in result['words']) {
    if (segments.isEmpty) {
      segments.add(TranscriptSegment(
          speaker: 'SPEAKER_${word['speaker']}',
          start: word['start'],
          end: word['end'],
          text: word['word'],
          isUser: false));
    } else {
      var lastSegment = segments.last;
      if (lastSegment.speakerId == word['speaker']) {
        lastSegment.text += ' ${word['word']}';
        lastSegment.end = word['end'];
      } else {
        segments.add(TranscriptSegment(
            speaker: 'SPEAKER_${word['speaker']}',
            start: word['start'],
            end: word['end'],
            text: word['word'],
            isUser: false));
      }
    }
  }
  return segments;
}

Future<List<Plugin>> retrievePlugins() async {
  var response = await makeApiCall(
    url: 'https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json',
    headers: {},
    body: '',
    method: 'GET',
  );
  if (response?.statusCode == 200) {
    try {
      return Plugin.fromJsonList(jsonDecode(response!.body));
    } catch (e, stackTrace) {
      CrashReporting.reportHandledCrash(e, stackTrace);
      return [];
    }
  }
  return [];
}

Future<String> devModeWebhookCall(Memory? memory) async {
  debugPrint('devModeWebhookCall: $memory');
  var url = SharedPreferencesUtil().webhookUrl;
  debugPrint('webhook url: $url');
  if (url.isEmpty || memory == null) return '';
  var data = memory.toJson();
  data['recordingFileBase64'] = await wavToBase64(memory.recordingFilePath ?? '');
  var response = await makeApiCall(
    url: url,
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(data),
    method: 'POST',
  );
  debugPrint('response: ${response?.statusCode}');
  var body = jsonDecode(response?.body ?? '{}');
  return body['message'] ?? '';
}

Future<String?> wavToBase64(String filePath) async {
  if (filePath.isEmpty) return null;
  try {
    // Read file as bytes
    File file = File(filePath);
    if (!file.existsSync()) {
      print('File does not exist: $filePath');
      return null;
    }
    List<int> fileBytes = await file.readAsBytes();

    // Encode bytes to base64
    String base64Encoded = base64Encode(fileBytes);

    return base64Encoded;
  } catch (e) {
    print('Error converting WAV to base64: $e');
    return null; // Handle error gracefully in your application
  }
}
