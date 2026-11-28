import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/home/home_model.dart';
import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/paywall/value_moment_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Everything a day holds over the plan's limit, as one row: locked conversations and held audio
/// together. Unlock opens the plans; a build that sells no plan says the recordings are kept, so the
/// row is never a dead end.
class HomeLockedRowView extends StatefulWidget {
  const HomeLockedRowView({super.key, required this.row});

  final HomeLockedRow row;

  @override
  State<HomeLockedRowView> createState() => _HomeLockedRowViewState();
}

class _HomeLockedRowViewState extends State<HomeLockedRowView> {
  @override
  void initState() {
    super.initState();
    // The free allowance locked something the reader can see: the cap offer, once (as the lone
    // locked conversation row did).
    final first = widget.row.conversations.firstOrNull;
    if (first == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || ModalRoute.of(context)?.isCurrent == false) return;
      ValueMomentPaywall.offer(PaywallMoment.freeCap, conversation: first, usage: context.read<UsageProvider?>());
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final plans = context.select<UsageProvider?, bool>((u) => u?.showSubscriptionUI == true);
    void open() => openHeldAudioPlans(context);
    return HomeRowShell(
      key: Key('home_locked_${widget.row.day.toIso8601String()}'),
      tile: HomeRowTile(child: Icon(Icons.lock_outline_rounded, size: 20, color: OmiColors.textSecondary)),
      title: l10n.homeLockedTitle(widget.row.count),
      subtitle: plans ? l10n.homeLockedSubtitle : l10n.homeLockedSubtitleNoPlans,
      trailing: plans ? HomeRowAction(label: l10n.unlock, onPressed: open) : null,
      onTap: plans ? open : null,
      actionTrailing: plans,
    );
  }
}
