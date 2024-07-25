import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:path_provider/path_provider.dart';

Future transcribeAfterStopiOS({
  required Function processFileToTranscript,
  required Function updateState,
  required Function memory,
  required List<TranscriptSegment> segments,
}) async {
  var path = await getApplicationDocumentsDirectory();
  var initalFile = File('${path.path}/recording_0.wav');
  if (initalFile.existsSync()) {
    // emptying the file instead of deleting incase if the user presses on start recording again after stopping
    initalFile.writeAsBytesSync([]);
  }
  var filePaths = [];
  var files = path.listSync();
  for (var file in files) {
    if (file is File) {
      if (!file.path.contains('recording_0')) {
        filePaths.add(file.path);
      }
    }
  }
  var filePathsToProcess = [];
  if (SharedPreferencesUtil().recordingPaths.isNotEmpty) {
    for (var f in filePaths) {
      if (!SharedPreferencesUtil().recordingPaths.contains(f)) {
        filePathsToProcess.add(f);
      }
    }
  } else {
    filePathsToProcess = [...filePaths];
  }
  if (filePathsToProcess.isNotEmpty) {
    Future.forEach(filePathsToProcess, (f) async {
      debugPrint('Processing file: $f');
      await processFileToTranscript(File(f));
      final file = File(f);
      if (file.existsSync()) {
        file.deleteSync();
        debugPrint('file deleted: $f');
      }
    }).then((value) async {
      debugPrint('All files processed in iOS');
      SharedPreferencesUtil().recordingPaths = [];
      updateState();
      if (segments.isNotEmpty) {
        debugPrint('segments not empty: ${segments.length} in iOS');
        memory();
      } else {
        debugPrint('segments empty in iOS');
      }
    });
  }
}

Future transcribeAfterStopAndroid(
    {required Function processFileToTranscript,
    required Function updateState,
    required Function memory,
    required List<TranscriptSegment> segments}) async {
  var path = await getApplicationDocumentsDirectory();
  var filePaths = [];
  var files = path.listSync();
  for (var file in files) {
    if (file is File) {
      if (file.path.contains('recording_')) {
        if (!SharedPreferencesUtil().recordingPaths.contains(file.path)) {
          filePaths.add(file.path);
        }
      }
    }
  }
  var filePathsToProcess = [];
  if (SharedPreferencesUtil().recordingPaths.isNotEmpty) {
    for (var f in filePaths) {
      if (!SharedPreferencesUtil().recordingPaths.contains(f)) {
        filePathsToProcess.add(f);
      }
    }
  } else {
    filePathsToProcess = [...filePaths];
  }
  if (filePathsToProcess.isNotEmpty) {
    Future.forEach(filePathsToProcess, (f) async {
      debugPrint('Processing file: $f');
      await processFileToTranscript(File(f));
      final file = File(f);
      if (file.existsSync()) {
        file.deleteSync();
        debugPrint('file deleted: $f');
      }
    }).then((value) async {
      debugPrint('All files processed in Android');
      SharedPreferencesUtil().recordingPaths = [];
      updateState();
      if (segments.isNotEmpty) {
        debugPrint('segments not empty: ${segments.length}');
        memory();
      } else {
        debugPrint('segments empty in Android');
      }
    });
  }
}

Future iosBgCallback({
  required bool shouldTranscribe,
  required int lastOffset,
  required int partNumber,
  required Function processFileToTranscript,
  required Function(int) updateState,
}) async {
  try {
    var path = await getApplicationDocumentsDirectory();
    var filePath = '${path.path}/recording_0.wav';
    final file = File(filePath);

    if (await file.exists()) {
      // Get the current length of the file
      final currentLength = await file.length();
      debugPrint('Current length: $currentLength and last offset: $lastOffset');
      if (currentLength > lastOffset) {
        // Read the new content from the file
        final content = await file.openRead(lastOffset, currentLength).toList();

        // Flatten the list of lists of bytes
        var newContent = content.expand((bytes) => bytes).toList();

        // Write the new content to a new file
        var path = await getApplicationDocumentsDirectory();
        final newFilePath = '${path.path}/recording_$partNumber.wav';
        final newFile = File(newFilePath);
        var header = WavBytesUtil.getWavHeader(newContent.length, 44100, channelCount: 2);
        newContent = [...header, ...newContent];
        await newFile.writeAsBytes((newContent));
        debugPrint('Triggered content written to $newFilePath');
        if (shouldTranscribe) {
          await processFileToTranscript(newFile);
          var paths = SharedPreferencesUtil().recordingPaths;
          SharedPreferencesUtil().recordingPaths = [...paths, newFilePath];
          if (newFile.existsSync()) {
            newFile.deleteSync();
            debugPrint('file deleted: $newFilePath');
          }
        }
        updateState(currentLength);
      }
    } else {
      debugPrint('File does not exist.');
    }
  } catch (e) {
    debugPrint('Error reading and splitting file content: $e');
  }
}

Future androidBgCallback({
  required FlutterBackgroundService backgroundService,
  required int fileCount,
  required Function updateState,
  required Function processFileToTranscript,
}) async {
  var path = await getApplicationDocumentsDirectory();
  var filePath = '${path.path}/recording_$fileCount.wav';
  var file = File(filePath);
  backgroundService.invoke('timerUpdate', {'time': '0'});
  if (file.existsSync()) {
    Future.delayed(const Duration(milliseconds: 500), () async {
      updateState();
      backgroundService.invoke('timerUpdate', {'time': '30'});
      await processFileToTranscript(file);
      var paths = SharedPreferencesUtil().recordingPaths;
      SharedPreferencesUtil().recordingPaths = [...paths, filePath];
      if (file.existsSync()) {
        file.deleteSync();
      }
      debugPrint('file deleted: $filePath');
    });
  } else {
    debugPrint('File does not exist.');
  }
}
