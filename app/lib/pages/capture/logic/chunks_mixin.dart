import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/api/transcribe.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:tuple/tuple.dart';

// Future<void> initiateBytesProcessing() async {
//   debugPrint('initiateBytesProcessing: $btDevice');
//   BleAudioCodec codec = await getAudioCodec(btDevice!.id);
//   if (codec == BleAudioCodec.unknown) {} // TODO: disconnect and show error
//
//   bool firstTranscriptMade = SharedPreferencesUtil().firstTranscriptMade;
//
//   audioStorage = WavBytesUtil(codec: codec);
//   await initiateChunksProcessing(
//     btDevice!.id,
//     codec,
//     audioStorage,
//     (newSegments, processedBytes) {
//       _handleNewSegments(newSegments);
//       if (segments.isEmpty) audioStorage!.removeFramesRange(fromSecond: 0, toSecond: processedBytes.length ~/ 100);
//       if (segments.isNotEmpty) elapsedSeconds += processedBytes.length ~/ 100;
//       if (segments.isNotEmpty && !firstTranscriptMade) {
//         SharedPreferencesUtil().firstTranscriptMade = true;
//         MixpanelManager().firstTranscriptMade();
//         firstTranscriptMade = true;
//       }
//     },
//     (bool value) => setState(() => isTranscribing = value),
//     _internetStatus,
//   );
// }

// _printFileSize(File file) async {
//   int bytes = await file.length();
//   var i = (log(bytes) / log(1024)).floor();
//   const suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
//   var size = '${(bytes / pow(1024, i)).toStringAsFixed(2)} ${suffixes[i]}';
//   debugPrint('File size: $size');
// }

// _processFileToTranscript(File f, {bool forceDeepgramTranscription = true}) async {
//   setState(() => isTranscribing = true);
//   print('transcribing file: ${f.path}');
//   await _printFileSize(f);
//   List<TranscriptSegment> newSegments;
//   if (SharedPreferencesUtil().useTranscriptServer && !forceDeepgramTranscription) {
//     newSegments = await transcribe(f);
//   } else {
//     newSegments = await deepgramTranscribe(f);
//   }
//   _handleNewSegments(newSegments);
//   setState(() => isTranscribing = false);
// }

// void _handleNewSegments(List<TranscriptSegment> newSegments) {
//   TranscriptSegment.combineSegments(segments, newSegments, toAddSeconds: elapsedSeconds); // combines b into a
//   if (newSegments.isNotEmpty) {
//     triggerTranscriptSegmentReceivedEvents(newSegments, conversationId, sendMessageToChat: sendMessageToChat);
//     SharedPreferencesUtil().transcriptSegments = segments;
//     setState(() {});
//     setHasTranscripts(true);
//     debugPrint('Memory creation timer restarted');
//     _memoryCreationTimer?.cancel();
//     _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
//     currentTranscriptStartedAt ??= DateTime.now().subtract(const Duration(seconds: 30));
//     currentTranscriptFinishedAt = DateTime.now();
//   }
//   // _doProcessingOfInstructions();
//   setState(() => isTranscribing = false);
// }

mixin AudioChunksMixin {
  Future<StreamSubscription?> initiateChunksProcessing(
    String deviceId,
    BleAudioCodec deviceCodec,
    WavBytesUtil? audioStorage,
    Function(List<TranscriptSegment>, List<List<int>>) onNewSegments,
    Function(bool) setIsTranscribing,
    InternetStatus? internetStatus,
  ) async {
    // BleAudioCodec codec = await getAudioCodec(deviceId);
    // if (codec == BleAudioCodec.unknown) {
    //   // TODO: disconnect and show error
    // }

    WavBytesUtil toProcessBytes2 = WavBytesUtil(codec: deviceCodec);
    return await getBleAudioBytesListener(
      deviceId,
      onAudioBytesReceived: (List<int> value) async {
        if (value.isEmpty) return;

        toProcessBytes2.storeFramePacket(value);
        audioStorage!.storeFramePacket(value);
        if (toProcessBytes2.hasFrames() && toProcessBytes2.frames.length % 3000 == 0) {
          if (internetStatus == InternetStatus.disconnected) {
            debugPrint('No internet connection, not processing audio');
            return;
          }
          if (await WavBytesUtil.tempWavExists()) return; // wait til that one is fully processed

          Tuple2<File, List<List<int>>> data = await toProcessBytes2.createWavFile(filename: 'temp.wav');
          try {
            setIsTranscribing(true);
            List<TranscriptSegment> newSegments = await _processFileToTranscript(data.item1);
            setIsTranscribing(false);
            onNewSegments(newSegments, data.item2);
          } catch (e, stacktrace) {
            debugPrint('Error processing 30 seconds frame');
            print(e);
            CrashReporting.reportHandledCrash(
              e,
              stacktrace,
              level: NonFatalExceptionLevel.warning,
              userAttributes: {'seconds': (data.item2.length ~/ 100).toString()},
            );
            toProcessBytes2.insertAudioBytes(data.item2);
          }
          WavBytesUtil.deleteTempWav();
        }
      },
    );
  }

  Future<List<TranscriptSegment>> _processFileToTranscript(File f) async {
    print('transcribing file: ${f.path}');
    _printFileSize(f);
    return await transcribe(f);
  }

  void _printFileSize(File file) async {
    int bytes = await file.length();
    var i = (log(bytes) / log(1024)).floor();
    const suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
    var size = '${(bytes / pow(1024, i)).toStringAsFixed(2)} ${suffixes[i]}';
    debugPrint('File size: $size');
  }
}
