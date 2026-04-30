import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/companion_stream_provider.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// The Companion Stream Home — Tab 0 of `ShellScreen`.
///
/// Layout (chat-pattern grammar):
///   ┌─────────────────────────────┐
///   │ Card stream (scrollable)    │
///   │   • voice cards (no chrome) │
///   │   • surface cards (chrome)  │
///   ├─────────────────────────────┤
///   │ Composer pill (docked)      │  <- tap → Chat tab
///   └─────────────────────────────┘
///
/// `CompanionStreamProvider` is screen-scoped — instantiated here, dies on
/// nav-away. Hive boxes are the durable source of truth.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.onSwitchToTab});

  /// Called by the composer pill to navigate from Home to another shell tab
  /// (Chat = 1). The shell owns tab state so we hand it a callback.
  final void Function(int tabIndex) onSwitchToTab;

  @override
  Widget build(BuildContext context) {
    final signals = context.read<OnboardingChatProvider>().signals;
    final actionItems = context.read<ActionItemsProvider>();
    return MultiProvider(
      providers: [
        Provider<HomeNav>.value(value: HomeNav(switchToTab: onSwitchToTab)),
        ChangeNotifierProvider<CompanionStreamProvider>(
          create: (_) => CompanionStreamProvider(
            signals: signals,
            actionItems: actionItems,
          ),
        ),
      ],
      child: _HomeBody(onSwitchToTab: onSwitchToTab),
    );
  }
}

class _HomeBody extends StatelessWidget {
  const _HomeBody({required this.onSwitchToTab});

  final void Function(int tabIndex) onSwitchToTab;

  @override
  Widget build(BuildContext context) {
    return Consumer<CompanionStreamProvider>(
      builder: (context, stream, _) {
        return Column(
          children: [
            Expanded(
              child: _CardList(cards: stream.cards),
            ),
            _Composer(
              onTap: () {
                onSwitchToTab(1); // Chat tab
              },
            ),
          ],
        );
      },
    );
  }
}

class _CardList extends StatelessWidget {
  const _CardList({required this.cards});

  final List<CompanionCard> cards;

  @override
  Widget build(BuildContext context) {
    if (cards.isEmpty) {
      return const _QuietEmpty();
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(
        AppStyles.spacingL,
        AppStyles.spacingXL,
        AppStyles.spacingL,
        AppStyles.spacingXL,
      ),
      itemCount: cards.length,
      separatorBuilder: (_, _) => const SizedBox(height: AppStyles.spacingL),
      itemBuilder: (context, i) => cards[i].render(context),
    );
  }
}

/// Cold-start empty state. Reached only if the welcome card was already
/// dismissed and no other cards exist (no v2 backend wired yet for action
/// items). Still polite, still in-voice.
class _QuietEmpty extends StatelessWidget {
  const _QuietEmpty();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppStyles.spacingXL),
        child: Text(
          "I'm here when you need me.",
          style: brandSerif(
            fontSize: 18,
            color: AppColors.textTertiary,
          ),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}

/// Pill-button composer that mirrors v1's `_AskNootoComposer`. NOT a real
/// `TextField` — taps push the Chat tab via the [onTap] callback. See design
/// doc §"Visual specification → Chat composer" for rationale.
class _Composer extends StatelessWidget {
  const _Composer({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          AppStyles.spacingS,
          AppStyles.spacingL,
          AppStyles.spacingS,
        ),
        child: Semantics(
          button: true,
          label: 'Ask Nooto anything. Opens chat.',
          child: Material(
            color: AppColors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
            child: InkWell(
              borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
              onTap: onTap,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 16,
                ),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.06),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: AppColors.brandPrimary.withValues(alpha: 0.15),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        FontAwesomeIcons.solidComment,
                        size: 16,
                        color: AppColors.brandPrimary,
                      ),
                    ),
                    const SizedBox(width: AppStyles.spacingM),
                    const Expanded(
                      child: Text(
                        'Ask Nooto anything…',
                        style: TextStyle(
                          fontSize: 16,
                          color: AppColors.textTertiary,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: AppStyles.spacingS),
                    const Icon(
                      Icons.arrow_forward_rounded,
                      size: 18,
                      color: AppColors.textTertiary,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
