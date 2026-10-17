import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/components/omi_icon_button.dart';
import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'memory_review_controller.dart';

export 'memory_review_controller.dart' show MemoryReviewController, MemoryReviewRowState, MemoryReviewSource;

/// Presents [MemoryReviewCard] in the app's sheet. The signature is a frozen seam shared across
/// screens: the daily recap opens its review through it. With the native preview the same review
/// renders as native rows over the same controller and provider.
Future<void> showMemoryReviewSheet(
  BuildContext context, {
  required List<MemoryReviewItem> items,
  required MemoryReviewSource source,
  String? impressionKey,
  String? title,
}) {
  return showOmiSheet<void>(
    context: context,
    builder: (_) => SingleChildScrollView(
      child: MemoryReviewCard(items: items, source: source, impressionKey: impressionKey, title: title),
    ),
    nativeBuilder: (_) =>
        _NativeMemoryReviewSheet(items: items, source: source, impressionKey: impressionKey, title: title),
  );
}

/// The native review sheet: the same rows as the chat transcript, over one controller that its
/// Flutter fallback shares, so a refused snapshot keeps every optimistic and settled row.
class _NativeMemoryReviewSheet extends StatefulWidget {
  const _NativeMemoryReviewSheet({required this.items, required this.source, this.impressionKey, this.title});

  final List<MemoryReviewItem> items;
  final MemoryReviewSource source;
  final String? impressionKey;
  final String? title;

  @override
  State<_NativeMemoryReviewSheet> createState() => _NativeMemoryReviewSheetState();
}

class _NativeMemoryReviewSheetState extends State<_NativeMemoryReviewSheet> {
  late final MemoryReviewController _controller =
      MemoryReviewController(items: widget.items, source: widget.source, impressionKey: widget.impressionKey);

  @override
  void initState() {
    super.initState();
    _controller.addListener(_changed);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = mounted ? _readProvider(context) : null;
      if (provider != null) _controller.startHydrationIfNeeded(provider);
    });
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _controller.removeListener(_changed);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final title = widget.title ?? l10n.memoryReviewTitle;
    return IosNativeSurface(
      title: title,
      fallback: OmiSheetScaffold(
        child: SingleChildScrollView(
          child: MemoryReviewCard(
            items: widget.items,
            source: widget.source,
            impressionKey: widget.impressionKey,
            title: widget.title,
            controller: _controller,
          ),
        ),
      ),
      toolbar: [
        NativeRow('memory_review_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('memory_review',
            nativeMemoryReviewRows(context, _controller, id: (part, index) => 'memory_${part}_$index')),
      ],
    );
  }
}

MemoriesProvider? _readProvider(BuildContext context, {bool listen = false}) {
  try {
    return listen ? context.watch<MemoriesProvider>() : context.read<MemoriesProvider>();
  } on ProviderNotFoundException {
    return null;
  }
}

/// The review rows for [controller]: one per item, a menu with Right, Wrong and Fix while it waits
/// for a verdict, and a label with its status once it has one. [id] names each row from a part and
/// an index, never from a memory id. A [header] adds the card title as a first label row. Without a
/// MemoriesProvider there is no mutation owner, so every row is a plain label.
List<NativeRow> nativeMemoryReviewRows(
  BuildContext context,
  MemoryReviewController controller, {
  required String Function(String part, int index) id,
  String? header,
}) {
  final l10n = context.l10n;
  final provider = _readProvider(context, listen: true);
  if (provider != null && controller.shouldRetryHydration(provider)) {
    WidgetsBinding.instance.addPostFrameCallback((_) => controller.startHydrationIfNeeded(provider));
  }
  return [
    if (header != null && controller.rows.isNotEmpty) NativeRow(id('reviewtitle', 0), header, kind: 'label'),
    for (final (index, item) in controller.rows.indexed)
      () {
        final memory = provider == null ? null : controller.memoryFor(provider, item.memoryId);
        final state = controller.stateFor(provider, memory, item.memoryId);
        final content = controller.contentOf(item, memory);
        final failed = controller.isFailed(item.memoryId) ? l10n.memoryReviewSaveFailed : '';
        if (provider == null || state != MemoryReviewRowState.pending) {
          return NativeRow(
            id('review', index),
            content,
            kind: 'label',
            symbol: switch (state) {
              MemoryReviewRowState.confirmed => 'checkmark.circle',
              MemoryReviewRowState.dropped => 'xmark.circle',
              MemoryReviewRowState.updated => 'pencil',
              MemoryReviewRowState.pending => null,
            },
            subtitle: [
              switch (state) {
                MemoryReviewRowState.confirmed => l10n.memoryReviewConfirmed,
                MemoryReviewRowState.dropped => l10n.memoryReviewDropped,
                MemoryReviewRowState.updated => l10n.memoryReviewUpdated,
                MemoryReviewRowState.pending => '',
              },
              item.categoryLabel,
              failed,
            ].where((line) => line.isNotEmpty).join('\n'),
          );
        }
        return NativeRow(
          id('review', index),
          content,
          kind: 'menu',
          subtitle: [item.categoryLabel, failed].where((line) => line.isNotEmpty).join('\n'),
          options: {'right': l10n.memoryReviewRight, 'wrong': l10n.memoryReviewWrong, 'fix': l10n.memoryReviewFix},
          enabled: !controller.isInFlight(item.memoryId),
          action: (value) => switch (value) {
            'right' => controller.review(provider, item, memory, true),
            'wrong' => controller.review(provider, item, memory, false),
            _ => _fix(context, controller, provider, item, memory),
          },
        );
      }(),
  ];
}

/// Fix: a guarded native editor prefilled with the row's text. Only Save writes, through the
/// controller; Cancel or a dismissal writes nothing. A text the editor cannot carry opens the Flutter
/// card for the row instead.
Future<void> _fix(BuildContext context, MemoryReviewController controller, MemoriesProvider provider,
    MemoryReviewItem item, Memory? memory) async {
  final l10n = context.l10n;
  controller.clearFailed(item.memoryId);
  final result = await showIosNativeModal(
    context,
    title: l10n.memoryReviewFix,
    guardEdits: true,
    actions: [NativeRow('cancel', l10n.cancel), NativeRow('save', l10n.save)],
    sections: [
      NativeSection('memory_fix', [
        NativeRow(
          'memory_fix_text',
          l10n.memoryReviewFix,
          kind: 'text',
          value: controller.contentOf(item, memory),
          maximumLength: 10000,
        ),
      ]),
    ],
  );
  if (result == null) {
    if (!context.mounted) return;
    await showOmiSheet<void>(
      context: context,
      builder: (_) => SingleChildScrollView(
        child: MemoryReviewCard(items: [item], source: controller.source, controller: controller),
      ),
    );
    return;
  }
  if (result.action != 'save') return;
  final value = result.values['memory_fix_text'];
  if (value is! String) return;
  await controller.saveEdit(provider, item, memory, value.trim());
}

/// "Things I learned today" — up to three memories Omi stored, each with
/// confirm / drop / correct controls.
///
/// The card owns no verdict state. Every row reads `userReview`/`edited` live
/// from [MemoriesProvider], which is the single mutation owner: a vote cast on
/// desktop shows here, and a vote cast here is not persisted in the chat
/// message or in preferences. A tap paints optimistically only until the
/// request returns, then the row goes back to reading the live memory.
///
/// A row whose id the provider has not loaded is still actionable: the item
/// carries the id and the recap text, and the provider's review and edit
/// requests are id-addressed. Such a row stays pending until a verdict is
/// written, and the card never renders untappable control chrome.
class MemoryReviewCard extends StatefulWidget {
  const MemoryReviewCard({
    super.key,
    required this.items,
    required this.source,
    this.impressionKey,
    this.title,
    this.controller,
  });

  final List<MemoryReviewItem> items;
  final MemoryReviewSource source;

  /// Stable identity for the shown-impression event. A chat card scrolled out
  /// and back rebuilds its State; without this the impression count would
  /// measure scrolling rather than reach.
  final String? impressionKey;

  /// Defaults to the localized "Things I learned today".
  final String? title;

  /// The review state of a native presentation this card stands in for. The card then shares it
  /// instead of owning one, and records no second impression.
  final MemoryReviewController? controller;

  @override
  State<MemoryReviewCard> createState() => _MemoryReviewCardState();
}

class _MemoryReviewCardState extends State<MemoryReviewCard> {
  late final MemoryReviewController _review = widget.controller ??
      MemoryReviewController(items: widget.items, source: widget.source, impressionKey: widget.impressionKey);
  final Map<String, TextEditingController> _editors = {};

  List<MemoryReviewItem> get _rows => widget.items.take(MemoryReviewCardBlock.maxItems).toList(growable: false);

  @override
  void initState() {
    super.initState();
    _review.addListener(_changed);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureMemoriesLoaded());
  }

  @override
  void didUpdateWidget(MemoryReviewCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.controller == null) _review.updateItems(widget.items);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    for (final controller in _editors.values) {
      controller.dispose();
    }
    _review.removeListener(_changed);
    if (widget.controller == null) _review.dispose();
    super.dispose();
  }

  MemoriesProvider? _memoriesProvider({required bool listen}) => _readProvider(context, listen: listen);

  /// Hydration is best-effort: the controls act by id regardless (see
  /// [MemoryReviewController.startHydrationIfNeeded]).
  void _ensureMemoriesLoaded() {
    _startHydrationIfNeeded();
  }

  void _startHydrationIfNeeded() {
    if (!mounted) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    _review.startHydrationIfNeeded(provider);
  }

  Memory? _memoryFor(MemoriesProvider provider, String memoryId) => _review.memoryFor(provider, memoryId);

  String _statusText(MemoryReviewRowState state) {
    final l10n = context.l10n;
    switch (state) {
      case MemoryReviewRowState.confirmed:
        return l10n.memoryReviewConfirmed;
      case MemoryReviewRowState.dropped:
        return l10n.memoryReviewDropped;
      case MemoryReviewRowState.updated:
        return l10n.memoryReviewUpdated;
      case MemoryReviewRowState.pending:
        return '';
    }
  }

  Future<void> _reviewRow(MemoryReviewItem item, Memory? memory, bool accepted) async {
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    await _review.review(provider, item, memory, accepted);
  }

  Future<void> _saveEdit(MemoryReviewItem item, Memory? memory) async {
    final controller = _editors[item.memoryId];
    final value = controller?.text.trim() ?? '';
    if (value.isEmpty || _review.isInFlight(item.memoryId)) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    final persisted = await _review.saveEdit(provider, item, memory, value);
    if (!mounted || !persisted) return;
    setState(() => _editors.remove(item.memoryId)?.dispose());
  }

  @override
  Widget build(BuildContext context) {
    final rows = _rows;
    if (rows.isEmpty) return const SizedBox.shrink();
    final provider = _memoriesProvider(listen: true);
    // A load that already settled in failure is the card's cue to spend its
    // capped retry: the initState ask started this load, and only a rebuild
    // observes how it settled.
    if (provider != null && _review.shouldRetryHydration(provider)) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _startHydrationIfNeeded());
    }

    return Column(
      key: const Key('memory_review_card'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(widget.title ?? context.l10n.memoryReviewTitle, style: OmiType.headline),
        const SizedBox(height: 10),
        ...rows.map((item) {
          final memory = provider == null ? null : _memoryFor(provider, item.memoryId);
          return _buildRow(item, provider, memory);
        }),
      ],
    );
  }

  Widget _buildRow(MemoryReviewItem item, MemoriesProvider? provider, Memory? memory) {
    final interactive = provider != null;
    final state = _review.stateFor(provider, memory, item.memoryId);
    final editing = _editors.containsKey(item.memoryId);
    final dimmed = state == MemoryReviewRowState.dropped;
    final content = _review.contentOf(item, memory);

    return Container(
      key: Key('memory_review_row_${item.memoryId}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Only the opacity changes when a row is dropped, so the list never
          // reflows under the user's finger.
          AnimatedOpacity(
            opacity: dimmed ? 0.45 : 1.0,
            duration: OmiMotion.of(context).quick,
            child: editing ? _buildEditor(item, memory) : Text(content, style: OmiType.subhead.copyWith(height: 1.35)),
          ),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
            child: Row(
              children: [
                if (item.categoryLabel.isNotEmpty) ...[
                  Text(
                    item.categoryLabel,
                    style: OmiType.caption.copyWith(color: OmiColors.textTertiary, letterSpacing: 0.3),
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  // Without a MemoriesProvider there is no mutation owner, so
                  // no controls render at all — never dead chrome.
                  child: interactive ? _buildTrailing(item, memory, state, editing) : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
          if (_review.isFailed(item.memoryId))
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                context.l10n.memoryReviewSaveFailed,
                key: Key('memory_review_error_${item.memoryId}'),
                style: OmiType.footnote.copyWith(color: OmiColors.warning),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildEditor(MemoryReviewItem item, Memory? memory) {
    final controller = _editors[item.memoryId]!;
    return TextField(
      key: Key('memory_review_editor_${item.memoryId}'),
      controller: controller,
      maxLines: 1,
      autofocus: true,
      style: OmiType.subhead,
      cursorColor: OmiColors.accent,
      decoration: InputDecoration(
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: 8),
        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: OmiColors.border)),
        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: OmiColors.accent)),
      ),
      onSubmitted: (_) => _saveEdit(item, memory),
    );
  }

  Widget _buildTrailing(MemoryReviewItem item, Memory? memory, MemoryReviewRowState state, bool editing) {
    if (editing) {
      return Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _control(
            key: Key('memory_review_cancel_${item.memoryId}'),
            label: context.l10n.cancel,
            onTap: () => setState(() => _editors.remove(item.memoryId)?.dispose()),
          ),
          const SizedBox(width: 8),
          _control(
            key: Key('memory_review_save_${item.memoryId}'),
            label: context.l10n.save,
            emphasized: true,
            onTap: _review.isInFlight(item.memoryId) ? null : () => _saveEdit(item, memory),
          ),
        ],
      );
    }

    if (state != MemoryReviewRowState.pending) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          _statusText(state),
          key: Key('memory_review_status_${item.memoryId}'),
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
        ),
      );
    }

    // Actionable by identity, not by list membership: the requests are
    // id-addressed and the item carries the id, so a row the provider never
    // loaded stays tappable. An in-flight write only disables its own row.
    final enabled = !_review.isInFlight(item.memoryId);
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        _control(
          key: Key('memory_review_accept_${item.memoryId}'),
          label: context.l10n.memoryReviewRight,
          onTap: enabled ? () => _reviewRow(item, memory, true) : null,
        ),
        const SizedBox(width: 8),
        _control(
          key: Key('memory_review_reject_${item.memoryId}'),
          label: context.l10n.memoryReviewWrong,
          onTap: enabled ? () => _reviewRow(item, memory, false) : null,
        ),
        const SizedBox(width: 8),
        _control(
          key: Key('memory_review_fix_${item.memoryId}'),
          label: context.l10n.memoryReviewFix,
          onTap: enabled
              ? () => setState(() {
                    _review.clearFailed(item.memoryId);
                    _editors[item.memoryId] = TextEditingController(text: _review.contentOf(item, memory));
                  })
              : null,
        ),
      ],
    );
  }

  /// A text control with a 44pt target (the painted label stays compact).
  Widget _control({required Key key, required String label, VoidCallback? onTap, bool emphasized = false}) {
    final color = onTap == null
        ? OmiColors.textDisabled
        : emphasized
            ? OmiColors.textPrimary
            : OmiColors.textSecondary;
    return Semantics(
      button: true,
      enabled: onTap != null,
      label: label,
      excludeSemantics: true,
      child: InkWell(
        key: key,
        onTap: onTap,
        borderRadius: OmiRadius.pillAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget, minWidth: kOmiMinTapTarget),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Center(
              widthFactor: 1,
              child: Text(
                label,
                style: OmiType.footnote.copyWith(
                  color: color,
                  fontWeight: emphasized ? FontWeight.w600 : FontWeight.w500,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
