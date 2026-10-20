import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/proactivity.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';
import 'package:omi/services/proactivity/proactivity_push.dart';
import 'package:omi/services/proactivity/proactivity_runtime.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef ProactivityFeedLoader = Future<ApiResult<GeneratedProactivityFeedResponse>> Function(String cursor);

Future<ApiResult<GeneratedProactivityFeedResponse>> _loadFeed(String cursor) {
  final epoch = ProactivityRuntime.outbox.epoch;
  return ProactivityApi(canSend: () => ProactivityRuntime.outbox.isCurrent(epoch)).feed(cursor: cursor);
}

/// A quiet, optional Home surface. The server owns availability and content.
class HomeForYou extends StatefulWidget {
  const HomeForYou({super.key, this.load = _loadFeed, this.outbox, this.open});
  final ProactivityFeedLoader load;
  final ProactivityOutbox? outbox;
  final ProactivityTargetOpener? open;

  @override
  State<HomeForYou> createState() => HomeForYouState();
}

class HomeForYouState extends State<HomeForYou> with WidgetsBindingObserver {
  late final ProactivityOutbox _outbox = widget.outbox ?? ProactivityRuntime.outbox;
  List<GeneratedProactivityFeedItem> _items = [];
  int _loadEpoch = 0;
  late int _ownerEpoch;
  final Set<String> _opening = {};

  @override
  void initState() {
    super.initState();
    _ownerEpoch = _outbox.epoch;
    _outbox.addListener(_changed);
    WidgetsBinding.instance.addObserver(this);
    unawaited(refresh());
  }

  void _changed() {
    if (!mounted) return;
    if (_ownerEpoch != _outbox.epoch) {
      _ownerEpoch = _outbox.epoch;
      _items = [];
      _opening.clear();
      unawaited(refresh());
    }
    setState(() {});
  }

  Future<void> refresh() async {
    final loadEpoch = ++_loadEpoch;
    final ownerEpoch = _outbox.epoch;
    if (!_outbox.isCurrent(ownerEpoch)) return;
    final items = <GeneratedProactivityFeedItem>[];
    var cursor = '';
    final cursors = <String>{};
    try {
      // Empty candidate pages may have a next cursor. Bound the optional read.
      for (var page = 0; page < 10; page++) {
        final result = await widget.load(cursor);
        if (!mounted || loadEpoch != _loadEpoch || !_outbox.isCurrent(ownerEpoch)) return;
        if (result is! ApiSuccess<GeneratedProactivityFeedResponse> || !result.data.enabled) {
          setState(() => _items = []);
          return;
        }
        items.addAll(result.data.items);
        if (items.isNotEmpty || !result.data.hasMore) break;
        cursor = result.data.nextCursor;
        if (cursor.isEmpty || !cursors.add(cursor)) break;
      }
      setState(() => _items = items);
    } catch (_) {
      if (mounted && loadEpoch == _loadEpoch && _outbox.isCurrent(ownerEpoch)) setState(() => _items = []);
    }
    unawaited(_outbox.flush());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(refresh());
  }

  @override
  void dispose() {
    _outbox.removeListener(_changed);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _open(GeneratedProactivityFeedItem item, int ownerEpoch) async {
    if (!_outbox.isCurrent(ownerEpoch)) return;
    if (!_opening.add(item.id)) return;
    final epoch = _outbox.epoch;
    await openProactivityTarget(item.id, item.target, outbox: _outbox, open: widget.open);
    if (_outbox.isCurrent(epoch)) _opening.remove(item.id);
  }

  @override
  Widget build(BuildContext context) {
    final items = _items
        .where(
          (i) =>
              !i.dismissed &&
              !_outbox.dismissed.contains(i.id) &&
              !_outbox.disabledProducers.contains(i.producer) &&
              proactivityTargetRoute(i.target) != null,
        )
        .toList();
    if (!_outbox.isCurrent(_ownerEpoch) || items.isEmpty) return const SizedBox.shrink();
    final current = ModalRoute.of(context)?.isCurrent ?? true;
    final ownerEpoch = _ownerEpoch;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.md),
            child: Semantics(header: true, child: Text(context.l10n.forYou, style: OmiType.headline)),
          ),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.md),
              child: current
                  ? VisibilityDetector(
                      key: ValueKey('for-you-visible-$_ownerEpoch-${item.id}'),
                      onVisibilityChanged: (info) {
                        final lifecycle = WidgetsBinding.instance.lifecycleState;
                        if (mounted &&
                            _outbox.isCurrent(ownerEpoch) &&
                            info.visibleFraction > 0 &&
                            (ModalRoute.of(context)?.isCurrent ?? true) &&
                            (lifecycle == null || lifecycle == AppLifecycleState.resumed)) {
                          unawaited(_outbox.record(item.id, ProactivityAction.shown));
                        }
                      },
                      child: _card(item),
                    )
                  : _card(item),
            ),
        ],
      ),
    );
  }

  Widget _card(GeneratedProactivityFeedItem item) {
    final ownerEpoch = _ownerEpoch;
    void record(ProactivityAction action, {String? producer}) {
      if (_outbox.isCurrent(ownerEpoch)) unawaited(_outbox.record(item.id, action, producer: producer));
    }

    final feedback = _outbox.feedback[item.id] ?? item.feedback;
    return Material(
      key: ValueKey('for-you-card-${item.id}'),
      color: OmiColors.surface1,
      borderRadius: BorderRadius.circular(OmiRadius.lg),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            key: ValueKey('for-you-open-${item.id}'),
            onTap: () => _open(item, ownerEpoch),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.title, style: OmiType.body.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: OmiSpacing.sm),
                  Text(item.body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, 0, OmiSpacing.xs, OmiSpacing.xs),
            child: Row(
              children: [
                Semantics(
                  selected: feedback == 'thumbs_up',
                  child: OmiIconButton(
                    key: ValueKey('for-you-up-${item.id}'),
                    label: context.l10n.helpful,
                    icon: FaIcon(feedback == 'thumbs_up' ? FontAwesomeIcons.solidThumbsUp : FontAwesomeIcons.thumbsUp),
                    onPressed: () {
                      if (feedback != 'thumbs_up') record(ProactivityAction.thumbsUp);
                    },
                  ),
                ),
                Semantics(
                  selected: feedback == 'thumbs_down',
                  child: OmiIconButton(
                    key: ValueKey('for-you-down-${item.id}'),
                    label: context.l10n.notHelpful,
                    icon: FaIcon(
                      feedback == 'thumbs_down' ? FontAwesomeIcons.solidThumbsDown : FontAwesomeIcons.thumbsDown,
                    ),
                    onPressed: () {
                      if (feedback != 'thumbs_down') record(ProactivityAction.thumbsDown);
                    },
                  ),
                ),
                const Spacer(),
                OmiButton.tertiary(
                  key: ValueKey('for-you-dismiss-${item.id}'),
                  label: context.l10n.dismiss,
                  size: OmiButtonSize.compact,
                  onPressed: () => record(ProactivityAction.dismissed),
                ),
                OmiIconButton(
                  key: ValueKey('for-you-more-${item.id}'),
                  label: context.l10n.moreOptions,
                  icon: const Icon(Icons.more_horiz),
                  onPressed: () => showOmiRowMenu(
                    context,
                    actions: [
                      OmiMenuAction(
                        icon: Icons.close,
                        label: context.l10n.stopThese,
                        onSelected: () => record(ProactivityAction.producerDisabled, producer: item.producer),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
