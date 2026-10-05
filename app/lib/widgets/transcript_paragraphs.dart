part of 'transcript.dart';

/// Saved-conversation paragraphs: a long turn starts a new paragraph once this many seconds have
/// passed since the paragraph began, and no paragraph holds more than [_maxLinesPerParagraph] lines.
const double _paragraphTimeGap = 60;
const int _maxLinesPerParagraph = 12;

/// Paragraph spacing, counting the list's 4 between rows: 24 between turns, 10 between the
/// paragraphs of one turn, and 8 above the first.
const double _paragraphFirstTop = 8;
const double _paragraphTurnTop = 14;
const double _paragraphBottom = 6;

/// While the current line is marked, every other line is drawn at this share of full ink.
const double _dimmedInkAlpha = 0.35;

/// A run of consecutive saved-conversation lines drawn as one paragraph: segment indexes
/// [first]..[last], under a name row when it [startsTurn] and a clock time when it [showsTime].
class _DetailParagraph {
  _DetailParagraph({required this.first, required this.last, required this.startsTurn, required this.showsTime});

  final int first;
  int last;
  final bool startsTurn;
  final bool showsTime;
}

/// Saved conversations: a speaker's turn drawn as one paragraph, each line still its own target.
extension _TranscriptParagraphs on _TranscriptWidgetState {
  /// Saved conversations draw a paragraph per row; every other transcript draws a row per segment.
  bool get _usesParagraphs => widget.isConversationDetail && widget.segmentBuilder == null;

  int get _rowCount => _usesParagraphs ? _paragraphs.length : widget.segments.length;

  int _rowOfSegment(int segmentIndex) {
    if (!_usesParagraphs) return segmentIndex;
    final row = _paragraphs.indexWhere((paragraph) => segmentIndex <= paragraph.last);
    return row < 0 ? max(0, _paragraphs.length - 1) : row;
  }

  /// Whether [data] starts a speaker's turn on a saved conversation: the speaker, their person or
  /// owner-ness changed, or it is Omi (each of Omi's lines is labelled).
  bool _startsTurn(TranscriptSegment? previous, TranscriptSegment data) =>
      previous == null ||
      previous.isUser != data.isUser ||
      previous.speakerId != data.speakerId ||
      previous.personId != data.personId ||
      (data.speakerId == omiSpeakerId && !data.isUser);

  /// Saved-conversation lines grouped into paragraphs. A speaker's turn reads as one paragraph, and a
  /// long turn starts a new one once [_paragraphTimeGap] has passed since the paragraph began, under
  /// its clock time when times can be shown. A line with a translation, or with the "Yes / Not
  /// <name>" question under it, ends its paragraph so the extra sits right below it, and no paragraph
  /// grows past [_maxLinesPerParagraph] lines, which keeps a long monologue from becoming one huge
  /// text layout.
  List<_DetailParagraph> _groupParagraphs(Set<String> askSegmentIds) {
    final segments = widget.segments;
    final paragraphs = <_DetailParagraph>[];
    for (var i = 0; i < segments.length; i++) {
      final data = segments[i];
      final previous = i > 0 ? segments[i - 1] : null;
      final open = paragraphs.isEmpty ? null : paragraphs.last;
      final startsTurn = _startsTurn(previous, data);
      if (open == null || previous == null) {
        paragraphs.add(_DetailParagraph(first: i, last: i, startsTurn: true, showsTime: true));
        continue;
      }
      final minuteLater = data.start - segments[open.first].start >= _paragraphTimeGap;
      final breaks = startsTurn ||
          minuteLater ||
          data.translations.isNotEmpty ||
          previous.translations.isNotEmpty ||
          askSegmentIds.contains(previous.id) ||
          i - open.first >= _maxLinesPerParagraph;
      if (breaks) {
        paragraphs
            .add(_DetailParagraph(first: i, last: i, startsTurn: startsTurn, showsTime: startsTurn || minuteLater));
      } else {
        open.last = i;
      }
    }
    return paragraphs;
  }

  /// The line's clock time ("12:40 PM") from [TranscriptWidget.startedAt], or its offset into the
  /// recording without one; null when the segments' timing can't be shown.
  String? _lineTime(TranscriptSegment data) {
    if (!widget.canDisplaySeconds) return null;
    final startedAt = widget.startedAt;
    if (startedAt == null) return OmiDuration.offset(data.start);
    return OmiDateFormat.of(context).time(startedAt.add(Duration(milliseconds: (data.start * 1000).round())));
  }

  /// One paragraph of a saved conversation (Omi v8 `.tt`, set as prose): who spoke and when, then the
  /// turn's lines flowing together, with no bubble or avatar. The name and time are 13/600 in the
  /// tertiary ink (the owner's in the primary ink, a voice nobody has named underlined with dots); the
  /// words are 17 pt at a 1.5 line in 80 % ink (the owner's in the primary ink). The marked line
  /// ([TranscriptWidget.highlightedSegmentId]) is full ink and every other line dims. Each line stays
  /// its own target: tapping it plays the recording from there, double-tapping it edits it, and
  /// tapping the name names the speaker.
  Widget _buildParagraph(
    _DetailParagraph paragraph,
    List<Person> people,
    SpeakerNames names,
    Set<String> askSegmentIds, {
    required bool isFirst,
  }) {
    final segments = widget.segments;
    final head = segments[paragraph.first];
    final Person? person = personById(people, head.personId);
    final lineIndexes = [for (var i = paragraph.first; i <= paragraph.last; i++) i];
    final isTagging = lineIndexes.any((i) => widget.taggingSegmentIds.contains(segments[i].id));
    final isOmi = head.speakerId == omiSpeakerId && !head.isUser;
    final unnamed = !head.isUser && !isOmi && (person == null || person.name.trim().isEmpty);
    final labelColor = head.isUser ? OmiColors.textPrimary : OmiColors.textTertiary;
    final label = OmiType.footnote.copyWith(color: labelColor, fontWeight: FontWeight.w600, height: 1.3);
    final name = names.forSegment(head, person: person);
    final time = paragraph.showsTime ? _lineTime(head) : null;
    final timeStyle = label.copyWith(
      fontWeight: FontWeight.w400,
      // A time inside a turn, with no name before it, stays quiet.
      color: paragraph.startsTurn ? labelColor : OmiColors.textTertiary,
      fontFeatures: const [FontFeature.tabularFigures()],
    );

    Widget? header;
    if (paragraph.startsTurn) {
      header = Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Flexible(
            child: _speakerTarget(
              head,
              name: name,
              Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: label.copyWith(
                  decoration: unnamed ? TextDecoration.underline : null,
                  decorationStyle: TextDecorationStyle.dotted,
                  decorationColor: labelColor,
                ),
              ),
            ),
          ),
          if (person != null && !isTagging) ...[
            const SizedBox(width: 4),
            SpeakerLabelBadge(source: head.speakerLabelSource),
          ],
          if (time != null) ...[const SizedBox(width: 8), Text(time, style: timeStyle)],
          if (isTagging) ...[const SizedBox(width: 6), const OmiSpinner(size: OmiSpinnerSize.small)],
        ],
      );
    } else if (time != null || isTagging) {
      header = Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          if (time != null) Text(time, style: timeStyle),
          if (isTagging) ...[if (time != null) const SizedBox(width: 6), const OmiSpinner(size: OmiSpinnerSize.small)],
        ],
      );
    }

    final seek = widget.onSegmentTap;
    final markedId = widget.highlightedSegmentId;
    final lineSpans = <InlineSpan>[];
    for (final i in lineIndexes) {
      final data = segments[i];
      final isCurrent = data.id == widget.currentSegmentId;
      final ink = markedId != null
          ? (data.id == markedId ? OmiColors.textPrimary : OmiColors.textPrimary.withValues(alpha: _dimmedInkAlpha))
          : (data.isUser ? OmiColors.textPrimary : OmiColors.textPrimary.withValues(alpha: 0.8));
      final style = TextStyle(color: ink);
      final recognizer = seek == null ? null : _lineTapRecognizer(data, seek);
      lineSpans.add(TextSpan(
        children: [
          if (i > paragraph.first) TextSpan(text: ' ', style: style, recognizer: recognizer),
          WidgetSpan(
            alignment: PlaceholderAlignment.top,
            child: _lineMarker(data, isCurrent: isCurrent, seekable: seek != null),
          ),
          // The word joiner keeps the marker on the same text line as the first word it marks.
          TextSpan(text: '⁠', style: style, recognizer: recognizer),
          for (final span in _lineWords(data, i))
            span is TextSpan ? TextSpan(text: span.text, style: style, recognizer: recognizer) : span,
        ],
      ));
    }
    // Character lengths of the lines, placeholders included, to map a text position back to its line.
    final lineLengths = [for (final span in lineSpans) span.toPlainText().length];
    final textKey = _paragraphTextKeys.putIfAbsent(head.id, GlobalKey.new);

    int lineAt(Offset globalPosition) {
      final render = textKey.currentContext?.findRenderObject();
      if (render is! RenderParagraph) return paragraph.first;
      var offset = render.getPositionForOffset(render.globalToLocal(globalPosition)).offset;
      for (var k = 0; k < lineLengths.length; k++) {
        if (offset < lineLengths[k]) return paragraph.first + k;
        offset -= lineLengths[k];
      }
      return paragraph.last;
    }

    void play(int segmentIndex) {
      HapticFeedback.lightImpact();
      seek!(segments[segmentIndex]);
    }

    final edit = widget.onEditSegmentText;
    // A tap on a line's words reaches that line's recognizer; this detector takes the gaps between
    // and after them, and double-taps. It lives inside the selection area so it outranks the area's
    // own gestures; a long press still selects.
    final words = SelectionArea(
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTapUp: seek == null ? null : (details) => play(lineAt(details.globalPosition)),
        onDoubleTapDown: edit == null ? null : (details) => _doubleTapPosition = details.globalPosition,
        onDoubleTap: edit == null
            ? null
            : () {
                HapticFeedback.mediumImpact();
                final position = _doubleTapPosition;
                edit(position == null ? paragraph.first : lineAt(position));
              },
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            RichText(
              key: textKey,
              textAlign: TextAlign.left,
              text: TextSpan(style: OmiType.body.copyWith(letterSpacing: 0.0, height: 1.5), children: lineSpans),
            ),
            // A line with translations is a paragraph of its own, so they sit right under it.
            if (head.translations.isNotEmpty) ...[
              for (final translation in head.translations)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    _getDecodedText(translation.text),
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontStyle: FontStyle.italic),
                    textAlign: TextAlign.left,
                  ),
                ),
              const SizedBox(height: 4),
              _buildTranslationNotice(),
            ],
          ],
        ),
      ),
    );

    // The question under the first line Omi named by voice ends its paragraph.
    final askLine = segments[paragraph.last];
    final askPerson = personById(people, askLine.personId);
    final confirm = widget.onConfirmSpeakerLabel;
    final reject = widget.onRejectSpeakerLabel;
    final asksToConfirm = askPerson != null &&
        confirm != null &&
        reject != null &&
        !widget.taggingSegmentIds.contains(askLine.id) &&
        askSegmentIds.contains(askLine.id);

    Widget body = Padding(
      padding: EdgeInsets.only(
        top: isFirst ? _paragraphFirstTop : (paragraph.startsTurn ? _paragraphTurnTop : 0),
        bottom: _paragraphBottom,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (header != null) ...[header, const SizedBox(height: 3)],
          words,
          if (asksToConfirm)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xxs),
              child: SpeakerLikelyConfirm(
                name: askPerson.name,
                onYes: () => confirm(askLine),
                onNot: () => reject(askLine),
              ),
            ),
        ],
      ),
    );
    if (seek != null) {
      // The rest of the row (its name row and padding) plays the paragraph from its first line.
      body = Semantics(
        hint: context.l10n.playFromHere,
        child: GestureDetector(behavior: HitTestBehavior.opaque, onTap: () => play(paragraph.first), child: body),
      );
    }
    // Assistive tech hears the paragraph holding the marked (else the playhead's) line as selected.
    final selectedId = markedId ?? widget.currentSegmentId;
    if (lineIndexes.any((i) => segments[i].id == selectedId)) {
      body = Semantics(selected: true, child: body);
    }
    return Container(
      padding: EdgeInsets.symmetric(horizontal: widget.horizontalMargin ? 16 : 0),
      child: body,
    );
  }

  /// A zero-size box at the start of a line's words. It carries the line's [_segmentKeys] entry, so
  /// following, locating, search and the reading line find each line inside its paragraph, plus the
  /// keys that name the line's tap target and the playing line.
  Widget _lineMarker(TranscriptSegment data, {required bool isCurrent, required bool seekable}) {
    Widget marker = const SizedBox.shrink();
    if (seekable) marker = KeyedSubtree(key: ValueKey('transcript_seek_${data.id}'), child: marker);
    if (isCurrent) marker = KeyedSubtree(key: ValueKey('transcript_current_${data.id}'), child: marker);
    return KeyedSubtree(key: _segmentKeys[data.id], child: marker);
  }

  /// The line's tap recognizer, kept per line for the widget's life (disposed with it) and pointed
  /// at this build's segment.
  TapGestureRecognizer _lineTapRecognizer(TranscriptSegment data, Function(TranscriptSegment) seek) {
    final recognizer = _lineTapRecognizers.putIfAbsent(data.id, TapGestureRecognizer.new);
    recognizer.onTap = () {
      HapticFeedback.lightImpact();
      seek(data);
    };
    return recognizer;
  }

  /// A line's words, with the current search's matches marked.
  List<InlineSpan> _lineWords(TranscriptSegment data, int segmentIndex) {
    final text = _getDecodedText(data.text);
    if (widget.searchQuery.isEmpty) return [TextSpan(text: text)];
    return _highlightSearchMatchesWithKeys(text, widget.searchQuery, segmentIndex);
  }
}
