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

/// The marked line sits on a bar that covers only its words, in full ink and a touch heavier; no
/// other line changes. The mark takes [_markFade] to pass from one line to the next.
const Duration _markFade = Duration(milliseconds: 200);

/// The marked line's extra weight: its ink drawn again this far to each side. A heavier font is
/// wider, so it would re-wrap the paragraph every time the mark moved.
const double _markedLineWeight = 0.2;

/// The bar reaches this far past the marked line's words on each side, and its corners are rounded.
const double _lineBarReach = 4;
const double _lineBarRadius = 5;

/// A run of consecutive saved-conversation lines drawn as one paragraph: segment indexes
/// [first]..[last], under a name row when it [startsTurn], a clock time when it [showsTime] and the
/// label badge when it [showsBadge].
class _DetailParagraph {
  _DetailParagraph({
    required this.first,
    required this.last,
    required this.startsTurn,
    required this.showsTime,
    required this.showsBadge,
  });

  final int first;
  int last;
  final bool startsTurn;
  final bool showsTime;
  final bool showsBadge;
}

/// Glues each line's zero-size marker to the line's first word, so a line break never falls between
/// them. Invisible, and dropped from copied text.
const String _wordJoiner = '\u2060';

/// What [SpeakerLabelBadge] draws for [source]: a check, "Likely", or nothing (null).
String? _badgeKind(String? source) =>
    SpeakerLabelSource.isConfirmed(source) ? 'confirmed' : (source == SpeakerLabelSource.auto ? 'likely' : null);

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
  /// its clock time when times can be shown. A line whose label badge differs from the line before
  /// (a check, then "Likely") starts one under that badge, with no name. A line with a translation,
  /// or with the "Yes / Not <name>" question under it, ends its paragraph so the extra sits right
  /// below it, and no paragraph grows past [_maxLinesPerParagraph] lines, which keeps a long
  /// monologue from becoming one huge text layout.
  List<_DetailParagraph> _groupParagraphs(Set<String> askSegmentIds) {
    final segments = widget.segments;
    final paragraphs = <_DetailParagraph>[];
    for (var i = 0; i < segments.length; i++) {
      final data = segments[i];
      final previous = i > 0 ? segments[i - 1] : null;
      final open = paragraphs.isEmpty ? null : paragraphs.last;
      final startsTurn = _startsTurn(previous, data);
      if (open == null || previous == null) {
        paragraphs.add(_DetailParagraph(first: i, last: i, startsTurn: true, showsTime: true, showsBadge: true));
        continue;
      }
      final minuteLater = data.start - segments[open.first].start >= _paragraphTimeGap;
      final badgeChanged =
          data.personId != null && _badgeKind(data.speakerLabelSource) != _badgeKind(previous.speakerLabelSource);
      final breaks = startsTurn ||
          minuteLater ||
          badgeChanged ||
          data.translations.isNotEmpty ||
          previous.translations.isNotEmpty ||
          askSegmentIds.contains(previous.id) ||
          i - open.first >= _maxLinesPerParagraph;
      if (breaks) {
        paragraphs.add(_DetailParagraph(
          first: i,
          last: i,
          startsTurn: startsTurn,
          showsTime: startsTurn || minuteLater,
          showsBadge: startsTurn || badgeChanged,
        ));
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
  /// ([TranscriptWidget.highlightedSegmentId]) sits on a bar, in full ink and a touch heavier. Each
  /// line stays its own target: tapping it plays the recording from there, double-tapping it edits
  /// it, and tapping the name names the speaker.
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
    } else {
      // Inside a turn: the badge where the label changed, the time after a minute, no name.
      final badge = paragraph.showsBadge && person != null && !isTagging && _badgeKind(head.speakerLabelSource) != null;
      if (badge || time != null || isTagging) {
        header = Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            if (badge) SpeakerLabelBadge(source: head.speakerLabelSource),
            if (time != null) ...[if (badge) const SizedBox(width: 8), Text(time, style: timeStyle)],
            if (isTagging) ...[
              if (time != null) const SizedBox(width: 6),
              const OmiSpinner(size: OmiSpinnerSize.small),
            ],
          ],
        );
      }
    }

    final seek = widget.onSegmentTap;
    final markedId = widget.highlightedSegmentId;
    // Each line's pieces, made once per build: its marker, then its text as one run (the joiner, its
    // words, then the space before the next line), so assistive tech stops once per line; only a
    // search match splits the run. The frames of a mark fade differ in nothing but the inks.
    final linePieces = <List<Object>>[];
    final recognizers = <TapGestureRecognizer?>[];
    final marked = lineIndexes.indexWhere((i) => segments[i].id == markedId);
    for (final i in lineIndexes) {
      final data = segments[i];
      final pieces = <Object>[
        WidgetSpan(
          alignment: PlaceholderAlignment.top,
          child: _lineMarker(data, isCurrent: data.id == widget.currentSegmentId, seekable: seek != null),
        ),
      ];
      var run = _wordJoiner;
      for (final span in _lineWords(data, i)) {
        if (span is TextSpan) {
          run += span.text ?? '';
          continue;
        }
        if (run == _wordJoiner) {
          // A line that opens on a search match: the joiner still glues the marker to it, unannounced.
          pieces.add(const TextSpan(text: _wordJoiner, semanticsLabel: ''));
        } else if (run.isNotEmpty) {
          pieces.add(run);
        }
        pieces.add(span);
        run = '';
      }
      if (i < paragraph.last) run += ' ';
      if (run.isNotEmpty) pieces.add(run);
      linePieces.add(pieces);
      recognizers.add(seek == null ? null : _lineTapRecognizer(data, seek));
    }
    final full = OmiColors.textPrimary;
    // The weight keeps one ink through a fade, so a frame of it never lays the text out again.
    final heavier = [
      Shadow(color: full, offset: const Offset(_markedLineWeight, 0)),
      Shadow(color: full, offset: const Offset(-_markedLineWeight, 0)),
    ];
    // [marks] is each line's share of the mark, from 0 (its resting ink) to 1 (full ink).
    TextStyle lineStyle(int k, double mark) => TextStyle(
          color: Color.lerp(_restingInk(lineIndexes[k]), full, mark),
          shadows: k == marked ? heavier : null,
        );
    List<InlineSpan> lineSpans(List<double> marks) => [
          for (var k = 0; k < linePieces.length; k++)
            TextSpan(
              children: [
                for (final piece in linePieces[k])
                  piece is String
                      ? TextSpan(text: piece, style: lineStyle(k, marks[k]), recognizer: recognizers[k])
                      : piece as InlineSpan,
              ],
            ),
        ];
    // Character lengths of the lines, placeholders included, to map a text position back to its line.
    final lineLengths = [
      for (final span in lineSpans(List.filled(linePieces.length, 0)))
        span.toPlainText(includeSemanticsLabels: false).length,
    ];
    // Each line's words in the paragraph's text: after its marker and joiner, before the space that
    // joins it to the next line.
    final wordRanges = <TextRange>[];
    var lineStart = 0;
    for (var k = 0; k < lineLengths.length; k++) {
      final lineEnd = lineStart + lineLengths[k];
      wordRanges.add(TextRange(start: lineStart + 2, end: k + 1 < lineLengths.length ? lineEnd - 1 : lineEnd));
      lineStart = lineEnd;
    }
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
            // Under the selection area, so a long press selects the words, and at the system text size.
            // The mark eases to the line it moved to, at once with Reduce Motion.
            _JoinerFreeSelection(
              child: _MarkFade(
                lines: lineIndexes.length,
                marked: marked,
                duration: MediaQuery.disableAnimationsOf(context) ? Duration.zero : _markFade,
                builder: (context, marks) => CustomPaint(
                  painter: _LineBarPainter(
                    textKey: textKey,
                    wordRanges: wordRanges,
                    marks: marks,
                    fill: OmiColors.surface3,
                  ),
                  child: RichText(
                    key: textKey,
                    textAlign: TextAlign.left,
                    textScaler: MediaQuery.textScalerOf(context),
                    selectionRegistrar: SelectionContainer.maybeOf(context),
                    selectionColor:
                        DefaultSelectionStyle.of(context).selectionColor ?? DefaultSelectionStyle.defaultColor,
                    text: TextSpan(
                      style: OmiType.body.copyWith(letterSpacing: 0.0, height: 1.5),
                      children: lineSpans(marks),
                    ),
                  ),
                ),
              ),
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

  /// The ink of the line at segment [index] while it is not marked: the owner's lines in full ink,
  /// everyone else's at 80 %.
  Color _restingInk(int index) =>
      widget.segments[index].isUser ? OmiColors.textPrimary : OmiColors.textPrimary.withValues(alpha: 0.8);

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

  /// A line's words, with the current search's matches marked. The paragraph already scales a match
  /// to the system text size, so the match's own text does not scale a second time.
  List<InlineSpan> _lineWords(TranscriptSegment data, int segmentIndex) {
    final text = _getDecodedText(data.text);
    if (widget.searchQuery.isEmpty) return [TextSpan(text: text)];
    return [
      for (final span in _highlightSearchMatchesWithKeys(text, widget.searchQuery, segmentIndex))
        span is WidgetSpan
            ? WidgetSpan(
                alignment: span.alignment,
                baseline: span.baseline,
                style: span.style,
                child: MediaQuery.withNoTextScaling(child: span.child),
              )
            : span,
    ];
  }
}

/// Cuts the list at its top and bottom, and [_lineBarReach] outside its left and right edges.
class _SideOpenClip extends CustomClipper<Rect> {
  const _SideOpenClip();

  @override
  Rect getClip(Size size) => Rect.fromLTRB(-_lineBarReach, 0, size.width + _lineBarReach, size.height);

  @override
  bool shouldReclip(_SideOpenClip oldClipper) => false;
}

/// A paragraph's selectable words: copying them leaves out the [_wordJoiner]s.
class _JoinerFreeSelection extends StatefulWidget {
  const _JoinerFreeSelection({required this.child});

  final Widget child;

  @override
  State<_JoinerFreeSelection> createState() => _JoinerFreeSelectionState();
}

class _JoinerFreeSelectionState extends State<_JoinerFreeSelection> {
  final _delegate = _JoinerFreeSelectionDelegate();

  @override
  void dispose() {
    _delegate.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SelectionContainer(delegate: _delegate, child: widget.child);
}

class _JoinerFreeSelectionDelegate extends StaticSelectionContainerDelegate {
  @override
  SelectedContent? getSelectedContent() {
    final content = super.getSelectedContent();
    return content == null ? null : SelectedContent(plainText: content.plainText.replaceAll(_wordJoiner, ''));
  }
}

/// Eases a paragraph's mark from the line it was on to line [marked] (-1 when the marked line is not
/// in this paragraph) over [duration], at once when that is zero. [builder] gets each line's share
/// of the mark, from 0 to 1.
class _MarkFade extends StatefulWidget {
  const _MarkFade({required this.lines, required this.marked, required this.duration, required this.builder});

  final int lines;
  final int marked;
  final Duration duration;
  final Widget Function(BuildContext context, List<double> marks) builder;

  @override
  State<_MarkFade> createState() => _MarkFadeState();
}

class _MarkFadeState extends State<_MarkFade> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, value: 1);
  List<double> _from = const [];

  /// The shares on screen now: part of the way from [_from] to [target]'s mark while a fade runs.
  List<double> _shown(_MarkFade target) => [
        for (var k = 0; k < target.lines; k++) _ease(k < _from.length ? _from[k] : 0, k == target.marked ? 1 : 0),
      ];

  double _ease(double from, double to) => from + (to - from) * _controller.value;

  @override
  void didUpdateWidget(_MarkFade oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.marked == widget.marked && oldWidget.lines == widget.lines) return;
    _from = _shown(oldWidget);
    // A paragraph that gained or lost a line has nothing to ease from.
    if (widget.duration == Duration.zero || oldWidget.lines != widget.lines) {
      _controller.value = 1;
    } else {
      _controller
        ..duration = widget.duration
        ..forward(from: 0);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => widget.builder(context, _shown(widget)),
      );
}

/// The bar behind the words of each line that holds a share of the mark, drawn at that share of
/// [fill]: one rounded outline around the line's text rows, which reaches [_lineBarReach] past the
/// words on each side.
class _LineBarPainter extends CustomPainter {
  _LineBarPainter({required this.textKey, required this.wordRanges, required this.marks, required this.fill});

  final GlobalKey textKey;
  final List<TextRange> wordRanges;
  final List<double> marks;
  final Color fill;

  @override
  void paint(Canvas canvas, Size size) {
    final text = textKey.currentContext?.findRenderObject();
    if (text is! RenderParagraph) return;
    for (var k = 0; k < wordRanges.length; k++) {
      if (marks[k] <= 0) continue;
      final rows = _rows(text, wordRanges[k]);
      final bar = Path();
      for (var first = 0, next = 1; next <= rows.length; next++) {
        // Two rows join into one outline when they share enough width for the corners between them.
        if (next < rows.length) {
          final shared = min(rows[next - 1].right, rows[next].right) - max(rows[next - 1].left, rows[next].left);
          if (shared >= 2 * _lineBarRadius) continue;
        }
        bar.addPath(_outline(rows.sublist(first, next)), Offset.zero);
        first = next;
      }
      canvas.drawPath(bar, Paint()..color = fill.withValues(alpha: fill.a * marks[k]));
    }
  }

  /// The text rows [words] cover, top to bottom, each [_lineBarReach] wider than its words on both
  /// sides and ending where the next begins.
  static List<Rect> _rows(RenderParagraph text, TextRange words) {
    // A text row can come back as several boxes: a search match or a change of direction splits it.
    final boxes = <Rect>[];
    for (final box in text.getBoxesForSelection(TextSelection(baseOffset: words.start, extentOffset: words.end))) {
      final rect = box.toRect();
      if (rect.width <= 0) continue;
      if (boxes.isNotEmpty && rect.center.dy > boxes.last.top && rect.center.dy < boxes.last.bottom) {
        boxes.last = boxes.last.expandToInclude(rect);
      } else {
        boxes.add(rect);
      }
    }
    return [
      for (var r = 0; r < boxes.length; r++)
        Rect.fromLTRB(
          boxes[r].left - _lineBarReach,
          boxes[r].top - 1,
          boxes[r].right + _lineBarReach,
          r + 1 < boxes.length ? boxes[r + 1].top - 1 : boxes[r].bottom + 1,
        ),
    ];
  }

  /// One outline around [rows]: along the top, down the right edges, along the bottom and back up
  /// the left edges, with every corner rounded by [_lineBarRadius].
  static Path _outline(List<Rect> rows) {
    final corners = [rows.first.topLeft, rows.first.topRight];
    for (var r = 0; r + 1 < rows.length; r++) {
      if (rows[r].right != rows[r + 1].right) {
        corners
          ..add(rows[r].bottomRight)
          ..add(Offset(rows[r + 1].right, rows[r].bottom));
      }
    }
    corners
      ..add(rows.last.bottomRight)
      ..add(rows.last.bottomLeft);
    for (var r = rows.length - 1; r > 0; r--) {
      if (rows[r].left != rows[r - 1].left) {
        corners
          ..add(rows[r].topLeft)
          ..add(Offset(rows[r - 1].left, rows[r].top));
      }
    }
    final outline = Path();
    for (var i = 0; i < corners.length; i++) {
      final corner = corners[i];
      // The rounding leaves each edge the radius from the corner, and never past the edge's middle.
      Offset toward(Offset neighbour) {
        final edge = neighbour - corner;
        return corner + edge / edge.distance * min(_lineBarRadius, edge.distance / 2);
      }

      final start = toward(corners[(i - 1) % corners.length]);
      final end = toward(corners[(i + 1) % corners.length]);
      if (i == 0) {
        outline.moveTo(start.dx, start.dy);
      } else {
        outline.lineTo(start.dx, start.dy);
      }
      // Every corner is a right angle, so this weight draws a quarter circle.
      outline.conicTo(corner.dx, corner.dy, end.dx, end.dy, sqrt1_2);
    }
    return outline..close();
  }

  @override
  bool shouldRepaint(_LineBarPainter oldDelegate) =>
      oldDelegate.fill != fill ||
      !listEquals(oldDelegate.marks, marks) ||
      !listEquals(oldDelegate.wordRanges, wordRanges);
}
