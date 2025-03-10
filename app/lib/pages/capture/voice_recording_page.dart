import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/pages/conversation_detail/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

class VoiceRecordingPage extends StatefulWidget {
  const VoiceRecordingPage({Key? key}) : super(key: key);

  @override
  State<VoiceRecordingPage> createState() => _VoiceRecordingPageState();
}

class _VoiceRecordingPageState extends State<VoiceRecordingPage> {
  final FlutterSoundRecorder _recorder = FlutterSoundRecorder();
  bool _isRecording = false;
  String _recordingFilePath = '';
  Timer? _recordingTimer;
  int _recordingDuration = 0;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _initRecorder();
  }

  Future<void> _initRecorder() async {
    final status = await Permission.microphone.request();
    if (status != PermissionStatus.granted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Microphone permission is required to record audio'),
        ),
      );
      return;
    }

    await _recorder.openRecorder();
    _recorder.setSubscriptionDuration(const Duration(milliseconds: 500));
  }

  Future<void> _startRecording() async {
    try {
      // Get the temporary directory
      final tempDir = await getTemporaryDirectory();
      _recordingFilePath = '${tempDir.path}/voice_recording_${const Uuid().v4()}.wav';

      // Start the recording
      await _recorder.startRecorder(
        toFile: _recordingFilePath,
        codec: Codec.pcm16WAV,
      );

      // Start the recording timer
      _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
        setState(() {
          _recordingDuration++;
        });
      });

      setState(() {
        _isRecording = true;
      });
    } catch (e) {
      debugPrint('Error starting recording: $e');
    }
  }

  Future<void> _stopRecording() async {
    try {
      await _recorder.stopRecorder();
      _recordingTimer?.cancel();

      setState(() {
        _isRecording = false;
      });

      // Process the recording
      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      await captureProvider.processPhoneRecording(_recordingFilePath);

      if (captureProvider.inProgressConversation != null) {
        // Navigate to the conversation detail page
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => ConversationDetailPage(
              conversation: captureProvider.inProgressConversation!,
            ),
          ),
        );
      }
    } catch (e) {
      debugPrint('Error stopping recording: $e');
    }
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _recorder.closeRecorder();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: scaffoldKey,
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Row(
          mainAxisSize: MainAxisSize.max,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            IconButton(
              onPressed: () {
                Navigator.pop(context);
              },
              icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
            ),
            const SizedBox(width: 4),
            const Text("🎙️"),
            const SizedBox(width: 4),
            const Expanded(child: Text("Voice Recording")),
          ],
        ),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_isRecording)
              Text(
                _formatDuration(_recordingDuration),
                style: const TextStyle(fontSize: 48, color: Colors.white),
              ),
            const SizedBox(height: 40),
            Container(
              height: 80,
              width: 80,
              decoration: BoxDecoration(
                color: _isRecording ? Colors.red : Colors.white,
                shape: BoxShape.circle,
              ),
              child: IconButton(
                icon: Icon(
                  _isRecording ? Icons.stop : Icons.mic,
                  size: 40,
                  color: _isRecording ? Colors.white : Colors.red,
                ),
                onPressed: _isRecording ? _stopRecording : _startRecording,
              ),
            ),
            const SizedBox(height: 40),
            Text(
              _isRecording ? "Tap to stop recording" : "Tap to start recording",
              style: const TextStyle(fontSize: 16, color: Colors.white),
            ),
          ],
        ),
      ),
    );
  }
} 