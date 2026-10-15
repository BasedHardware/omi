import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/review.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';

typedef ReviewChangesLoader = Future<ApiResult<ReviewChangesPage>> Function({String? cursor});
typedef ReviewChangeToggler = Future<ApiResult<ReviewChange>> Function(String changeId, {required bool undone});

/// What Omi changed on its own in the last 30 days, each with its reason and an Undo. A back-office
/// screen reached from Review; nothing here is pushed at the user.
class RecentChangesPage extends StatefulWidget {
  const RecentChangesPage({super.key, this.loadChanges, this.setUndone});

  final ReviewChangesLoader? loadChanges;
  final ReviewChangeToggler? setUndone;

  @override
  State<RecentChangesPage> createState() => _RecentChangesPageState();
}

class _RecentChangesPageState extends State<RecentChangesPage> {
  List<ReviewChange> _changes = const [];
  String? _cursor;
  bool _loading = true;
  bool _failed = false;
  bool _loadingMore = false;
  final Set<String> _busy = {};

  ReviewChangesLoader get _load => widget.loadChanges ?? api.getReviewChanges;
  ReviewChangeToggler get _toggle => widget.setUndone ?? api.setReviewChangeUndone;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    final result = await _load();
    if (!mounted) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiSuccess(:final data):
          _changes = data.changes;
          _cursor = data.nextCursor;
        case ApiFailure():
          _failed = true;
      }
    });
  }

  Future<void> _more() async {
    final cursor = _cursor;
    if (cursor == null || _loadingMore) return;
    setState(() => _loadingMore = true);
    final result = await _load(cursor: cursor);
    if (!mounted) return;
    setState(() {
      _loadingMore = false;
      if (result case ApiSuccess(:final data)) {
        _changes = [..._changes, ...data.changes];
        _cursor = data.nextCursor;
      }
    });
  }

  Future<void> _setUndone(ReviewChange change, bool undone) async {
    final failed = context.l10n.reviewChangeFailed;
    setState(() => _busy.add(change.changeId));
    final result = await _toggle(change.changeId, undone: undone);
    if (!mounted) return;
    setState(() {
      _busy.remove(change.changeId);
      if (result case ApiSuccess(:final data)) {
        _changes = [for (final c in _changes) c.changeId == data.changeId ? data : c];
      }
    });
    if (result is ApiFailure) OmiFeedback.error(context, failed);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final Widget body;
    if (_loading) {
      body = const OmiLoadingState();
    } else if (_failed) {
      body = OmiErrorState(message: l10n.reviewChangesLoadFailed, onRetry: _refresh);
    } else if (_changes.isEmpty) {
      body = OmiEmptyState(icon: Icons.history, title: l10n.reviewNoChangesTitle, message: l10n.reviewNoChangesBody);
    } else {
      final dates = OmiDateFormat.of(context);
      final rows = <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.xxs, OmiSpacing.xs),
          child: Text(l10n.reviewChangesIntro, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ),
      ];
      String? lastHeader;
      for (final change in _changes) {
        final header = dates.dayHeader(change.createdAt);
        if (header != lastHeader) {
          lastHeader = header;
          rows.add(_DayHeader(label: header));
        }
        rows.add(_ChangeRow(
          change: change,
          busy: _busy.contains(change.changeId),
          onToggle: () => _setUndone(change, !change.undone),
        ));
      }
      if (_cursor != null) {
        rows.add(Center(
          child: OmiButton.tertiary(label: l10n.reviewShowMore, isLoading: _loadingMore, onPressed: _more),
        ));
      }
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: rows,
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.reviewRecentChanges)),
      body: body,
    );
  }
}

class _DayHeader extends StatelessWidget {
  const _DayHeader({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.sm, OmiSpacing.xxs, OmiSpacing.xs),
      child: Semantics(
        header: true,
        child: Text(
          label.toUpperCase(),
          style: OmiType.footnote
              .copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary, letterSpacing: 0.4),
        ),
      ),
    );
  }
}

IconData _changeIcon(ReviewChangeKind kind) => switch (kind) {
      ReviewChangeKind.rename => Icons.spellcheck,
      ReviewChangeKind.mergeMemories => Icons.call_merge,
      ReviewChangeKind.updatePerson => Icons.person_outline,
      ReviewChangeKind.labelSpeaker => Icons.record_voice_over_outlined,
      ReviewChangeKind.titleConversation => Icons.edit_outlined,
      ReviewChangeKind.closeTask => Icons.task_alt,
      ReviewChangeKind.other => Icons.auto_fix_high_outlined,
    };

class _ChangeRow extends StatelessWidget {
  const _ChangeRow({required this.change, required this.busy, required this.onToggle});

  final ReviewChange change;
  final bool busy;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final undone = change.undone;
    return Container(
      key: ValueKey('review_change_${change.changeId}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 14, OmiSpacing.xs, 14),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(undone ? Icons.undo : _changeIcon(change.kind), size: 18, color: OmiColors.textSecondary),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                  child: Text(change.title,
                      style: undone
                          ? OmiType.subhead
                              .copyWith(color: OmiColors.textSecondary, decoration: TextDecoration.lineThrough)
                          : OmiType.subhead.copyWith(fontWeight: FontWeight.w600))),
            ],
          ),
          if (undone)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xxs),
                child: Text(l10n.reviewChangeUndone, style: OmiType.footnote)),
          if (change.before != null && change.before!.isNotEmpty)
            _ChangeValue(label: l10n.reviewChangeBefore, value: change.before!, fieldKey: 'before'),
          if (change.after != null)
            _ChangeValue(
                label: l10n.reviewChangeAfter,
                value: change.after!.isEmpty ? l10n.reviewChangeRemoved : change.after!,
                fieldKey: 'after'),
          if (change.refs.any((ref) => ref.label.isNotEmpty))
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xs),
                child: Text(change.refs.map((ref) => ref.label).where((label) => label.isNotEmpty).toSet().join(' · '),
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
          if (change.context != null)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.sm),
                child: ReviewSpellingContext(context: change.context!)),
          if (change.context == null && change.snippet != null)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xs),
                child: Text(change.snippet!, style: OmiType.footnote)),
          if (change.reason != null)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xs),
                child: Text(change.reason!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
          Align(
              alignment: Alignment.centerRight,
              child: OmiButton.tertiary(
                  key: ValueKey('review_change_toggle_${change.changeId}'),
                  label: undone ? l10n.redo : l10n.undo,
                  isLoading: busy,
                  onPressed: busy ? null : onToggle)),
        ],
      ),
    );
  }
}

class _ChangeValue extends StatelessWidget {
  const _ChangeValue({required this.label, required this.value, required this.fieldKey});
  final String label;
  final String value;
  final String fieldKey;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(top: OmiSpacing.xs),
        padding: const EdgeInsets.all(OmiSpacing.sm),
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.xxs),
          Text(value, key: ValueKey('review_change_$fieldKey'), style: OmiType.subhead),
        ]),
      );
}
