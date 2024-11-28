import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/gen/assets.gen.dart';

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool horizontalMargin;
  final bool topMargin;
  final bool separator;
  final bool canDisplaySeconds;
  final bool isMemoryDetail;
  final Function(int)? editSegment;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.horizontalMargin = true,
    this.topMargin = true,
    this.separator = true,
    this.canDisplaySeconds = true,
    this.isMemoryDetail = false,
    this.editSegment,
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
      separatorBuilder: (_, __) => SizedBox(height: widget.separator ? 16.0 : 0),
      itemBuilder: (context, idx) {
        if (idx == 0) return SizedBox(height: widget.topMargin ? 32 : 0);
        if (idx == widget.segments.length + 1) return const SizedBox(height: 64);
        final data = widget.segments[idx - 1];

        var text = data.text;
        try {
          text = utf8.decode(data.text.toString().codeUnits);
        } catch (e) {}
        Person? person = data.personId != null ? SharedPreferencesUtil().getPersonById(data.personId!) : null;
        return Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
              widget.horizontalMargin ? 16 : 0, 0.0, widget.horizontalMargin ? 16 : 0, 0.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              GestureDetector(
                // onTap: () {
                //   widget.editSegment?.call(idx - 1);
                //   MixpanelManager().assignSheetOpened();
                // },
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Image.asset(
                      data.isUser
                          ? Assets.images.speaker0Icon.path
                          : person != null
                              ? speakerImagePath[person.colorIdx!]
                              : Assets.images.speaker1Icon.path,
                      width: 26,
                      height: 26,
                    ),
                    const SizedBox(width: 12),
                    Text(
                      data.isUser
                          ? SharedPreferencesUtil().givenName.isNotEmpty
                              ? SharedPreferencesUtil().givenName
                              : 'You'
                          : data.personId != null
                              ? person?.name ?? 'Deleted Person'
                              : 'Speaker ${data.speakerId}',
                      style: const TextStyle(
                          //  person != null ? speakerColors[person.colorIdx!] :
                          color: Colors.white,
                          fontSize: 18),
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
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: SelectionArea(
                  child: Text(
                    tryDecodingText(text),
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

class LiteTranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;

  const LiteTranscriptWidget({
    super.key,
    required this.segments,
  });

  @override
  State<LiteTranscriptWidget> createState() => _LiteTranscriptWidgetState();
}

class _LiteTranscriptWidgetState extends State<LiteTranscriptWidget> {
  @override
  Widget build(BuildContext context) {
    if (widget.segments.isEmpty) {
      return const SizedBox.shrink();
    }

    var text = getLastTranscript(widget.segments, maxCount: 70, includeTimestamps: false);
    text = text.replaceAll(RegExp(r"\s+|\n+"), " "); // trim before pushing to 1 line text view
    return Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
      textAlign: TextAlign.right,
    );
  }
}

String getLastTranscript(List<TranscriptSegment> transcriptSegments,
    {int? maxCount, bool generate = false, bool includeTimestamps = true}) {
  var transcript = TranscriptSegment.segmentsAsString(transcriptSegments, includeTimestamps: includeTimestamps);
  if (maxCount != null) transcript = transcript.substring(max(transcript.length - maxCount, 0));
  try {
    return utf8.decode(transcript.codeUnits);
  } catch (e) {
    return transcript;
  }
}

String tryDecodingText(String text) {
  try {
    return utf8.decode(text.toString().codeUnits);
  } catch (e) {
    return text;
  }
}
