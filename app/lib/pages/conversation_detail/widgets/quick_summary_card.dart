import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/interim_summary.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/widgets/note_sections_sliver.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The phone's live-preview lines as transcript segments, for a pendant session that has no server
/// transcript at Finish. Times are seconds from the earliest line; untimed lines count one each.
List<TranscriptSegment> transcriptFromPreview(List<LivePreviewLine> lines) {
  DateTime? origin;
  for (final line in lines) {
    final started = line.startedAt;
    if (started != null && (origin == null || started.isBefore(origin))) origin = started;
  }
  double offset(DateTime? at, double fallback) =>
      origin == null || at == null ? fallback : at.difference(origin).inMilliseconds / 1000;
  return [
    for (final (index, line) in lines.indexed)
      if (line.text.trim().isNotEmpty)
        TranscriptSegment(
          id: 'preview-${line.id}',
          text: line.text.trim(),
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: offset(line.startedAt, index.toDouble()),
          end: offset(line.endedAt, index + 1.0),
          translations: [],
        ),
  ];
}

/// Splits the streamed Markdown into a '# title' and '## heading' sections; text before any heading
/// forms a heading-less section.
({String title, List<Section> sections}) parseQuickSummary(String text) {
  var title = '';
  final sections = <({String heading, List<String> body})>[];
  final heading = RegExp(r'^(#{1,6})\s*(.*)$');
  for (final raw in text.split('\n')) {
    final line = raw.trimRight();
    final match = heading.firstMatch(line.trimLeft());
    if (match != null) {
      final words = match.group(2)!.trim();
      if (match.group(1)!.length == 1) {
        title = words;
      } else {
        sections.add((heading: words, body: []));
      }
      continue;
    }
    if (line.trim().isEmpty) continue;
    if (sections.isEmpty) sections.add((heading: '', body: []));
    sections.last.body.add(line);
  }
  return (
    title: title,
    sections: [
      for (final section in sections)
        if (section.heading.isNotEmpty || section.body.isNotEmpty)
          Section(heading: section.heading, bodyMarkdown: section.body.join('\n')),
    ],
  );
}

/// A short summary streamed from the transcript and drawn like the full notes, until the full
/// summary replaces it. Display only: nothing is saved.
class QuickSummarySliver extends StatefulWidget {
  const QuickSummarySliver({
    super.key,
    required this.conversation,
    this.onPoll,
    this.pollInterval = const Duration(seconds: 3),
    this.streamSummary,
  });

  final ServerConversation conversation;

  /// Called every [pollInterval] while shown, so the page picks up the full summary.
  final Future<void> Function()? onPoll;
  final Duration pollInterval;

  @visibleForTesting
  final Stream<InterimSummaryEvent> Function()? streamSummary;

  /// Written this app session, so reopening the page does not stream again.
  static final Map<String, String> _written = {};

  /// Pages that showed a Quick Summary; their full summary fades in.
  static final Set<String> _shown = {};

  /// Titles by conversation, shown in the page header while the stored title is empty.
  static final ValueNotifier<Map<String, String>> titles = ValueNotifier(const {});

  /// True once per conversation whose page showed a Quick Summary.
  static bool takeHandoff(String conversationId) => _shown.remove(conversationId);

  @visibleForTesting
  static void debugClearCache() {
    _written.clear();
    _shown.clear();
    titles.value = const {};
  }

  @override
  State<QuickSummarySliver> createState() => _QuickSummarySliverState();
}

class _QuickSummarySliverState extends State<QuickSummarySliver> {
  StreamSubscription<InterimSummaryEvent>? _subscription;
  Timer? _poll;
  String _text = '';
  bool _failed = false;

  String get _id => widget.conversation.id;

  @override
  void initState() {
    super.initState();
    final written = QuickSummarySliver._written[_id];
    if (written != null) {
      _text = written;
      // The header listens to titles: publish after this frame, not during it.
      WidgetsBinding.instance.addPostFrameCallback((_) => _publishTitle());
    } else {
      _subscription = _open().listen(_onEvent, onError: (Object _) => _onEvent(const InterimSummaryError('stream')));
    }
    if (widget.onPoll != null) _poll = Timer.periodic(widget.pollInterval, (_) => widget.onPoll!());
  }

  Stream<InterimSummaryEvent> _open() {
    final override = widget.streamSummary;
    if (override != null) return override();
    final conversation = widget.conversation;
    return Stream.fromFuture(getUsageDeviceTimeZone()).asyncExpand(
      (timezone) => streamInterimSummary(
        conversationId: conversation.id,
        // Empty segments: the server uses the stored transcript.
        segments: conversation.transcriptSegments,
        startedAt: conversation.startedAt,
        timezone: timezone,
      ),
    );
  }

  void _publishTitle() {
    if (!mounted) return;
    final title = parseQuickSummary(_text).title;
    if (title.isEmpty || QuickSummarySliver.titles.value[_id] == title) return;
    QuickSummarySliver.titles.value = {...QuickSummarySliver.titles.value, _id: title};
  }

  void _onEvent(InterimSummaryEvent event) {
    if (!mounted) return;
    setState(() {
      switch (event) {
        case InterimSummaryDelta(:final text):
          _text += text;
        case InterimSummaryDone():
          if (_text.trim().isNotEmpty) QuickSummarySliver._written[_id] = _text;
        case InterimSummaryError():
          _failed = true;
        case InterimSummaryStart():
          break;
      }
    });
    _publishTitle();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _poll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sections = parseQuickSummary(_text).sections;
    if (sections.isNotEmpty) QuickSummarySliver._shown.add(_id);
    return SliverMainAxisGroup(
      key: const Key('quick_summary'),
      slivers: [
        if (sections.isNotEmpty)
          NoteSectionsSliver(sections: sections, transcriptSegments: widget.conversation.transcriptSegments)
        else if (!_failed)
          const SliverToBoxAdapter(child: _SectionPlaceholder()),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.lg),
            child: Row(key: const Key('quick_summary_full_pending'), children: [
              OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textTertiary),
              const SizedBox(width: OmiSpacing.xs),
              Text(context.l10n.quickSummaryWritingFullSummary,
                  style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
            ]),
          ),
        ),
      ],
    );
  }
}

/// A heading bar over two lines where the first section will appear.
class _SectionPlaceholder extends StatelessWidget {
  const _SectionPlaceholder();

  Widget _bar(double width, double height) => Container(
        width: width,
        height: height,
        decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
      );

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 27, bottom: OmiSpacing.sm),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _bar(160, 16),
        const SizedBox(height: OmiSpacing.md),
        _bar(double.infinity, 12),
        const SizedBox(height: OmiSpacing.xs),
        _bar(220, 12),
      ]),
    );
  }
}

/// The full summary, faded in once when it replaces a Quick Summary on the same page.
class QuickSummaryHandoff extends StatefulWidget {
  const QuickSummaryHandoff({super.key, required this.conversationId, required this.sliver});

  final String conversationId;
  final Widget sliver;

  @override
  State<QuickSummaryHandoff> createState() => _QuickSummaryHandoffState();
}

class _QuickSummaryHandoffState extends State<QuickSummaryHandoff> with SingleTickerProviderStateMixin {
  late final AnimationController _fade;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    final handoff = QuickSummarySliver.takeHandoff(widget.conversationId);
    _fade = AnimationController(vsync: this, duration: const Duration(milliseconds: 450), value: handoff ? 0 : 1);
    _opacity = CurvedAnimation(parent: _fade, curve: Curves.easeOut);
    if (handoff) _fade.forward();
  }

  @override
  void dispose() {
    _fade.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SliverFadeTransition(opacity: _opacity, sliver: widget.sliver);
}
