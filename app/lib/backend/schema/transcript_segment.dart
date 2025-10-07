import 'package:omi/backend/preferences.dart';

class Translation {
  String lang;
  String text;

  Translation({
    required this.lang,
    required this.text,
  });

  factory Translation.fromJson(Map<String, dynamic> json) {
    return Translation(
      lang: json['lang'] as String,
      text: json['text'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'lang': lang,
      'text': text,
    };
  }

  static List<Translation> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => Translation.fromJson(e)).toList();
  }
}

class TranscriptSegment {
  String id;
  late int idx;

  String text;
  String? speaker;
  late int speakerId;
  bool isUser;
  String? personId;
  double start;
  double end;
  List<Translation> translations = [];
  bool speechProfileProcessed;
  String? rawText;
  String? enhancedText;

  TranscriptSegment({
    required this.id,
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.personId,
    required this.start,
    required this.end,
    required this.translations,
    this.speechProfileProcessed = true,
    this.rawText,
    this.enhancedText,
  }) {
    speakerId = speaker != null ? int.parse(speaker!.split('_')[1]) : 0;
    text = text.trim();
    rawText = (rawText ?? text).trim();
    enhancedText = enhancedText?.trim();
    if (enhancedText != null && enhancedText!.isEmpty) {
      enhancedText = null;
    }
    if (enhancedText != null) {
      text = enhancedText!;
    }
  }

  @override
  String toString() {
    return 'TranscriptSegment: {id: $id text: $text, speaker: $speakerId, isUser: $isUser, start: $start, end: $end}';
  }

  bool get isEnhanced => enhancedText != null && enhancedText!.isNotEmpty;

  String get displayText {
    if (enhancedText != null && enhancedText!.isNotEmpty) {
      return enhancedText!;
    }
    if (rawText != null && rawText!.isNotEmpty) {
      return rawText!;
    }
    return text;
  }

  void setEnhancedText(String? value) {
    final cleaned = value?.trim();
    if (cleaned == null || cleaned.isEmpty) {
      enhancedText = null;
      text = (rawText ?? text).trim();
      return;
    }
    enhancedText = cleaned;
    text = cleaned;
  }

  String getTimestampString() {
    final startDuration = Duration(seconds: start.toInt());
    final endDuration = Duration(seconds: end.toInt());
    return '${startDuration.inHours.toString().padLeft(2, '0')}:${(startDuration.inMinutes % 60).toString().padLeft(2, '0')}:${(startDuration.inSeconds % 60).toString().padLeft(2, '0')} - ${endDuration.inHours.toString().padLeft(2, '0')}:${(endDuration.inMinutes % 60).toString().padLeft(2, '0')}:${(endDuration.inSeconds % 60).toString().padLeft(2, '0')}';
  }

  factory TranscriptSegment.fromJson(Map<String, dynamic> json) {
    return TranscriptSegment(
      id: (json['id'] ?? '') as String,
      text: json['text'] as String,
      speaker: (json['speaker'] ?? 'SPEAKER_00') as String,
      isUser: (json['is_user'] ?? false) as bool,
      personId: json['person_id'],
      start: double.tryParse(json['start'].toString()) ?? 0.0,
      end: double.tryParse(json['end'].toString()) ?? 0.0,
      translations: json['translations'] != null ? Translation.fromJsonList(json['translations'] as List<dynamic>) : [],
      speechProfileProcessed: (json['speech_profile_processed'] ?? true) as bool,
      rawText: json['raw_text'] as String?,
      enhancedText: json['enhanced_text'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'text': text,
      'speaker': speaker,
      'speaker_id': speakerId,
      'is_user': isUser,
      'start': start,
      'end': end,
      'translations': translations.map((t) => t.toJson()).toList(),
      'speech_profile_processed': speechProfileProcessed,
      'raw_text': rawText,
      'enhanced_text': enhancedText,
    };
  }

  static List<TranscriptSegment> fromJsonList(List<dynamic> jsonList) {
    final List<TranscriptSegment> segments = [];
    for (int i = 0; i < jsonList.length; i++) {
      final segment = TranscriptSegment.fromJson(jsonList[i]);
      segment.idx = i;
      segments.add(segment);
    }
    return segments;
  }

  static List<TranscriptSegment> updateSegments(
      List<TranscriptSegment> segments, List<TranscriptSegment> updateSegments) {
    if (updateSegments.isEmpty) return [];

    if (segments.isEmpty) return updateSegments;

    final Map<String, TranscriptSegment> updateSegmentMap = {};
    for (var segment in updateSegments) {
      updateSegmentMap[segment.id] = segment;
    }
    for (int i = 0; i < segments.length; i++) {
      final segmentId = segments[i].id;
      if (updateSegmentMap.containsKey(segmentId)) {
        segments[i] = updateSegmentMap[segmentId]!;
        updateSegmentMap.remove(segmentId);
      }
    }

    return updateSegments.where((segment) => updateSegmentMap.containsKey(segment.id)).toList();
  }

  static void _appendSegment(TranscriptSegment target, TranscriptSegment source) {
    target.text = '${target.text} ${source.text}'.trim();

    final targetRaw = (target.rawText ?? target.text).trim();
    final sourceRaw = (source.rawText ?? source.text).trim();
    target.rawText = '$targetRaw $sourceRaw'.trim();

    if (source.enhancedText != null && source.enhancedText!.isNotEmpty) {
      final joined = <String>[];
      if (target.enhancedText != null && target.enhancedText!.isNotEmpty) {
        joined.add(target.enhancedText!);
      }
      joined.add(source.enhancedText!);
      final mergedEnhanced = joined.join(' ').trim();
      target.setEnhancedText(mergedEnhanced);
    }

    target.end = source.end;
  }

  static combineSegments(
    List<TranscriptSegment> segments,
    List<TranscriptSegment> newSegments, {
    int toAddSeconds = 0,
    double toRemoveSeconds = 0,
  }) {
    if (newSegments.isEmpty) return;

    for (var segment in newSegments) {
      segment.start -= toRemoveSeconds;
      segment.end -= toRemoveSeconds;

      segment.start += toAddSeconds;
      segment.end += toAddSeconds;
    }

    final joinedSimilarSegments = <TranscriptSegment>[];
    for (var newSegment in newSegments) {
      final isNotEmpty = joinedSimilarSegments.isNotEmpty;
      final isSameUser = isNotEmpty && joinedSimilarSegments.last.isUser == newSegment.isUser;
      final isSameSpeaker = isNotEmpty && joinedSimilarSegments.last.speaker == newSegment.speaker;

      if (isNotEmpty && isSameSpeaker && isSameUser) {
        _appendSegment(joinedSimilarSegments.last, newSegment);
      } else {
        joinedSimilarSegments.add(newSegment);
      }
    }

    if (joinedSimilarSegments.isEmpty) return;

    final existingNotEmpty = segments.isNotEmpty;
    final sameUser = existingNotEmpty && segments.last.isUser == joinedSimilarSegments[0].isUser;
    final sameSpeaker = existingNotEmpty && segments.last.speaker == joinedSimilarSegments[0].speaker;
    final withinThreshold = existingNotEmpty && (joinedSimilarSegments[0].start - segments.last.end < 30);

    if (existingNotEmpty && sameSpeaker && sameUser && withinThreshold) {
      _appendSegment(segments.last, joinedSimilarSegments[0]);
      joinedSimilarSegments.removeAt(0);
    }

    segments.addAll(joinedSimilarSegments);

    for (var i = 0; i < segments.length; i++) {
      segments[i].text =
          segments[i].text.trim().replaceAll('  ', ' ').replaceAll(' ,', ',').replaceAll(' .', '.').replaceAll(' ?', '?');
      segments[i].rawText = (segments[i].rawText ?? segments[i].text).trim();
      if (segments[i].enhancedText != null) {
        final cleaned = segments[i].enhancedText!.trim();
        segments[i].setEnhancedText(cleaned.isEmpty ? null : cleaned);
      }
    }
  }

  static String segmentsAsString(
    List<TranscriptSegment> segments, {
    bool includeTimestamps = false,
  }) {
    String transcript = '';
    final userName = SharedPreferencesUtil().givenName;
    final people = SharedPreferencesUtil().cachedPeople;
    final peopleMap = {for (var p in people) p.id: p.name};

    includeTimestamps = includeTimestamps && TranscriptSegment.canDisplaySeconds(segments);
    for (var segment in segments) {
      final segmentText = segment.displayText.trim();
      final timestampStr = includeTimestamps ? '[${segment.getTimestampString()}]' : '';
      if (segment.isUser) {
        transcript += '$timestampStr ${userName.isEmpty ? 'User' : userName}: $segmentText ';
      } else {
        String speakerName;
        if (segment.personId != null && peopleMap.containsKey(segment.personId)) {
          speakerName = peopleMap[segment.personId]!;
        } else {
          speakerName = 'Speaker ${segment.speakerId}';
        }
        transcript += '$timestampStr $speakerName: $segmentText ';
      }
      transcript += '\n\n';
    }
    return transcript.trim();
  }

  static bool canDisplaySeconds(List<TranscriptSegment> segments) {
    for (var i = 0; i < segments.length; i++) {
      for (var j = i + 1; j < segments.length; j++) {
        if (segments[i].start > segments[j].end || segments[i].end > segments[j].start) {
          return false;
        }
      }
    }
    return true;
  }
}
