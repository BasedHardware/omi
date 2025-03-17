import 'package:flutter/material.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:provider/provider.dart';

class ChatMicButton extends StatefulWidget {
  final TextEditingController textController;
  final Function(String) onTextChanged;

  const ChatMicButton({
    super.key,
    required this.textController,
    required this.onTextChanged,
  });

  @override
  State<ChatMicButton> createState() => _ChatMicButtonState();
}

class _ChatMicButtonState extends State<ChatMicButton> {
  void _toggleRecording(BuildContext context, CaptureProvider provider) async {
    var recordingState = provider.recordingState;

    if (recordingState == RecordingState.record) {
      await provider.stopStreamRecording();
    } else if (recordingState == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      widget.textController.clear();

      provider.clearTranscripts();
      provider.segments.clear();
      provider.updateRecordingState(RecordingState.initialising);

      await provider.streamRecording();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
        builder: (context, captureProvider, child) {
      final bool isInitializing =
          captureProvider.recordingState == RecordingState.initialising;

      final bool isRecording =
          captureProvider.recordingState == RecordingState.record;

      if (captureProvider.hasTranscripts && isRecording) {
        // Get text from segments
        String transcribedText = captureProvider.segments.last.text;
        // Update text field if we have new text
        if (transcribedText.isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            widget.textController.text = transcribedText;
            widget.onTextChanged(widget.textController.text);
          });
        }
      }
      return IconButton(
        onPressed: () => _toggleRecording(context, captureProvider),
        icon: isInitializing
            ? const SizedBox(
                height: 24,
                width: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : Icon(
                isRecording ? Icons.stop : Icons.mic,
                color: isRecording ? Colors.red : Colors.grey,
              ),
      );
    });
  }
}
