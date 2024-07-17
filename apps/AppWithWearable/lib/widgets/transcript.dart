import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool horizontalMargin;
  final bool topMargin;
  final bool canDisplaySeconds;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.horizontalMargin = true,
    this.topMargin = true,
    this.canDisplaySeconds = true,
  });

  @override
  State<TranscriptWidget> createState() => _TranscriptWidgetState();
}

class _TranscriptWidgetState extends State<TranscriptWidget> {
  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: widget.segments.length + 2,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
        if (idx == widget.segments.length + 1) return const SizedBox(height: 64);
        final data = widget.segments[idx - 1];

        return Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
              widget.horizontalMargin ? 16 : 0, 0.0, widget.horizontalMargin ? 16 : 0, 0.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Image.asset(data.isUser ? 'assets/images/speaker_0_icon.png' : 'assets/images/speaker_1_icon.png',
                      width: 26, height: 26),
                  const SizedBox(width: 12),
                  Text(
                    data.isUser
                        ? SharedPreferencesUtil().givenName.isNotEmpty
                            ? SharedPreferencesUtil().givenName
                            : 'You'
                        : 'Speaker ${data.speakerId}',
                    style: const TextStyle(color: Colors.white, fontSize: 18),
                  ),
                  widget.canDisplaySeconds ? const SizedBox(width: 12) : const SizedBox(),
                  // pad as start-end as hours:minutes:seconds e.g. 01:23:45
                  widget.canDisplaySeconds
                      ? Text(
                          data.getTimestampString(),
                          style: const TextStyle(color: Colors.grey, fontSize: 14),
                        )
                      : const SizedBox(),
                ],
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: SelectionArea(
                  child: Text(
                    utf8.decode(data.text.toString().codeUnits, allowMalformed: true),
                    style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                    textAlign: TextAlign.left,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
