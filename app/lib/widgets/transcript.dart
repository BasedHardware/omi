import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool horizontalMargin;
  final bool topMargin;
  final bool separator;
  final bool canDisplaySeconds;
  final bool isConversationDetail;
  final Function(int, int)? editSegment;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.horizontalMargin = true,
    this.topMargin = true,
    this.separator = true,
    this.canDisplaySeconds = true,
    this.isConversationDetail = false,
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
                onTap: () {
                  widget.editSegment?.call(idx - 1, data.speakerId);
                  MixpanelManager().assignSheetOpened();
                },
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
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        tryDecodingText(text),
                        style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                        textAlign: TextAlign.left,
                      ),
                      if (data.translations.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        ...data.translations.map((translation) => Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Text(
                                tryDecodingText(translation.text),
                                style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                                textAlign: TextAlign.left,
                              ),
                            )),
                        const SizedBox(height: 4),
                        GestureDetector(
                          onTap: () {
                            showDialog(
                              context: context,
                              builder: (BuildContext context) {
                                return AlertDialog(
                                  title: const Text('Translation Notice'),
                                  content: const Text(
                                    'Omi translates conversations into your primary language. Update it anytime in Settings →  Profiles.',
                                    style: TextStyle(fontSize: 14),
                                  ),
                                  actions: [
                                    TextButton(
                                      child: const Text('OK'),
                                      onPressed: () {
                                        Navigator.of(context).pop();
                                      },
                                    ),
                                  ],
                                );
                              },
                            );
                          },
                          child: Opacity(
                            opacity: 0.5,
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.check_circle,
                                  size: 12,
                                  color: Colors.grey,
                                ),
                                SizedBox(width: 4),
                                Text(
                                  'translated by omi',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey,
                                    fontStyle: FontStyle.italic,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ],
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

String formatChatTimestamp(DateTime dateTime) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);

  if (messageDate == today) {
    // Today, show time only
    return dateTimeFormat('h:mm a', dateTime);
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    return 'Yesterday ${dateTimeFormat('h:mm a', dateTime)}';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
