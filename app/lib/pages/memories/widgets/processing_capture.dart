import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/providers/capture_provider.dart' show CaptureProvider;
import 'package:friend_private/utils/enums.dart' hide RecordingSource;
import 'package:friend_private/services/watch_manager.dart';

class ProcessingCapture extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, WatchManager>(
      builder: (context, captureProvider, watchManager, _) {
        final isWatchRecording =
          captureProvider.recordingSource == CaptureProvider.RecordingSource.watch;

        Widget recordingIcon;
        String recordingText;

        switch (captureProvider.recordingSource) {
          case CaptureProvider.RecordingSource.necklace:
            recordingIcon = const Icon(Icons.mic, color: Colors.red);
            recordingText = 'Recording from Necklace';
            break;
          case CaptureProvider.RecordingSource.watch:
            recordingIcon = const Icon(Icons.watch, color: Colors.red);
            recordingText = 'Recording from Watch';
            break;
          case CaptureProvider.RecordingSource.phone:
            recordingIcon = const Icon(Icons.phone_android, color: Colors.red);
            recordingText = 'Recording from Phone';
            break;
          default:
            recordingIcon = const Icon(Icons.error_outline);
            recordingText = 'Unknown Recording Source';
        }

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.grey.withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
              recordingIcon,
              const SizedBox(width: 8),
              Expanded(
                child: Text(recordingText),
              ),
              if (isWatchRecording && watchManager.isRecording)
                const Icon(Icons.graphic_eq, color: Colors.red),
            ],
          ),
        );
      },
    );
  }
}
