import 'package:flutter/material.dart';

import 'package:omi/backend/schema/transcript_segment.dart';

class LiveTranscriptDisplay extends StatelessWidget {
  final List<TranscriptSegment> segments;

  const LiveTranscriptDisplay({super.key, required this.segments});

  @override
  Widget build(BuildContext context) {
    if (segments.isEmpty) {
      return const Center(
        child: Text(
          'Start speaking...',
          style: TextStyle(color: Color(0xFF666666), fontSize: 16, fontStyle: FontStyle.italic),
        ),
      );
    }

    final text = segments.map((s) => s.text).join(' ');

    return SingleChildScrollView(
      reverse: true,
      child: AnimatedSize(
        duration: const Duration(milliseconds: 200),
        alignment: Alignment.topCenter,
        child: Text(
          text,
          style: const TextStyle(color: Colors.white, fontSize: 20, height: 1.5),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
