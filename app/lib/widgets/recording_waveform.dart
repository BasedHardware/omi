import 'package:flutter/material.dart';
import 'package:siri_wave/siri_wave.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

class RecordingWaveform extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool isRecording;
  final double height;

  const RecordingWaveform({
    super.key,
    required this.segments,
    required this.isRecording,
    this.height = 80,
  });

  @override
  State<RecordingWaveform> createState() => _RecordingWaveformState();
}

class _RecordingWaveformState extends State<RecordingWaveform> {
  late IOS9SiriWaveformController _controller;

  @override
  void initState() {
    super.initState();
    _controller = IOS9SiriWaveformController(
      amplitude: 1.0, // Start with higher amplitude (10x more)
      color1: const Color(0xFF00FFFF), // Cyan for futuristic feel
      color2: const Color(0xFF8B5CF6),
      color3: const Color(0xFFFF00FF), // Magenta for vibrancy
      speed: 0.08, // Slow speed as requested
    );
  }

  @override
  void didUpdateWidget(RecordingWaveform oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (widget.isRecording != oldWidget.isRecording || widget.segments.length != oldWidget.segments.length) {
      _updateWaveformAmplitude();
    }
  }

  void _updateWaveformAmplitude() {
    if (!widget.isRecording) {
      // Not recording - low amplitude (10x more visible)
      _controller.amplitude = 0.3;
      return;
    }

    // Check if there's speech activity - if we have segments, assume active speech
    bool hasRecentSpeech = widget.segments.isNotEmpty;

    if (hasRecentSpeech) {
      // Active speech - much higher amplitude with variation (10x more visible)
      _controller.amplitude = 10.0 + (DateTime.now().millisecond % 100) * 0.03;
    } else {
      // Recording but no recent speech - medium amplitude (10x more visible)
      _controller.amplitude = 1.5;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isRecording) {
      return SizedBox(
        height: widget.height,
        child: Center(
          child: Text(
            'Start recording to see waveform',
            style: TextStyle(
              color: Colors.grey.shade600,
              fontSize: 12,
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.fromLTRB(14, 14, 14, 0),
      height: widget.height,
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A).withOpacity(0.3),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: const Color(0xFF6366F1).withOpacity(0.2),
          width: 1,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SiriWaveform.ios9(
          controller: _controller,
          options: IOS9SiriWaveformOptions(
            height: widget.height,
            width: double.infinity,
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    super.dispose();
  }
}
