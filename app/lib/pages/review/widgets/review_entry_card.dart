import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/review/review_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The Home entry to Review. Shown only while there is something to answer; it disappears once
/// the user is caught up.
///
/// Review absorbs the older single-purpose prompt cards, so while Review is off for the account
/// (or not yet known) [fallback] is shown in its place instead.
class ReviewEntryCard extends StatefulWidget {
  const ReviewEntryCard({super.key, this.fallback});

  final Widget? fallback;

  @override
  State<ReviewEntryCard> createState() => _ReviewEntryCardState();
}

class _ReviewEntryCardState extends State<ReviewEntryCard> {
  @override
  void initState() {
    super.initState();
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
    if (provider == null || !provider.isOn) return widget.fallback ?? const SizedBox.shrink();
    if (provider.items.isEmpty) return const SizedBox.shrink();
    final count = provider.items.length;
    final title = context.l10n.reviewEntryTitle;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 15, OmiSpacing.md, 0),
      child: Semantics(
        button: true,
        label: '$title, $count',
        excludeSemantics: true,
        child: Material(
          key: const Key('review_entry_card'),
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          child: InkWell(
            borderRadius: OmiRadius.lgAll,
            onTap: () => routeToPage(context, const ReviewPage()),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
              child: Row(
                children: [
                  SizedBox(
                    width: 40,
                    height: 40,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                          child: Icon(Icons.record_voice_over_outlined, size: 20, color: OmiColors.textPrimary),
                        ),
                        Positioned(
                          top: -2,
                          right: -2,
                          child: Container(
                            constraints: const BoxConstraints(minWidth: 18),
                            height: 18,
                            padding: const EdgeInsets.symmetric(horizontal: 5),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
                            child: Text(
                              '$count',
                              style: OmiType.caption.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w700),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(child: Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600))),
                  Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
