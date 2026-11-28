import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Home entry to the questions only the user can answer. With none waiting it draws nothing: the
/// applied-change history lives in Activity, behind Home's bell.
///
/// Review replaced the older single-purpose prompt cards (the speaker prompt card was deleted on
/// 2026-10-23). While Review is off or not yet known it draws nothing.
class ReviewEntryCard extends StatefulWidget {
  const ReviewEntryCard({super.key});

  @override
  State<ReviewEntryCard> createState() => _ReviewEntryCardState();
}

class _ReviewEntryCardState extends State<ReviewEntryCard> with WidgetsBindingObserver {
  /// The card hides when nothing is waiting, so it cannot be the only way new questions arrive:
  /// coming back to the app looks again, at most this often.
  static const _resumeRefreshInterval = Duration(minutes: 5);
  DateTime _lastLoad = DateTime.now();

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    if (DateTime.now().difference(_lastLoad) < _resumeRefreshInterval) return;
    final provider = context.read<ReviewProvider?>();
    if (provider == null || provider.availability == ReviewAvailability.off) return;
    _lastLoad = DateTime.now();
    provider.load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final provider = context.read<ReviewProvider?>();
      provider?.reportReleaseChannel();
      if (provider != null && provider.availability == ReviewAvailability.unknown) provider.load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ReviewProvider?>();
    if (provider == null || !provider.isOn) return const SizedBox.shrink();
    final count = provider.items.length;
    if (count == 0) return const SizedBox.shrink();
    final title = context.l10n.reviewEntryTitle;
    return HomeRowShell(
      key: const Key('review_entry_card'),
      tile: HomeRowTile(child: Icon(Icons.record_voice_over_outlined, size: 20, color: OmiColors.textPrimary)),
      title: title,
      semanticsLabel: '$title, $count',
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            constraints: const BoxConstraints(minWidth: 22),
            height: 22,
            padding: const EdgeInsets.symmetric(horizontal: 6),
            alignment: Alignment.center,
            decoration: BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
            child: Text(
              '$count',
              style: OmiType.caption.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(width: OmiSpacing.xs),
          HomeRowShell.chevron(),
        ],
      ),
      onTap: () => routeToPage(context, const ReviewPage()),
    );
  }
}
