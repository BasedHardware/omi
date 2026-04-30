import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/companion_stream_provider.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/services/chat_service.dart';
import 'package:nooto_v2/shell/app_bar_kebab_menu.dart';
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
    final chatService = context.read<ChatService>();
    return MultiProvider(
      providers: [
        Provider<HomeNav>.value(value: HomeNav(switchToTab: onSwitchToTab)),
        ChangeNotifierProvider<CompanionStreamProvider>(
          create: (_) => CompanionStreamProvider(
            signals: signals,
            actionItems: actionItems,
            chatService: chatService,
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
              child: _CardScroll(cards: stream.cards),
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

/// CustomScrollView with the iOS Large Title pattern:
/// the Nooto wordmark sits large at the top of the cards and collapses into
/// the compact bar as you scroll. CupertinoSliverNavigationBar gives the
/// authentic cross-fade between large and compact titles plus the iOS 26
/// Liquid Glass blur material automatically.
class _CardScroll extends StatelessWidget {
  const _CardScroll({required this.cards});

  final List<CompanionCard> cards;

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        CupertinoSliverNavigationBar(
          backgroundColor: AppColors.backgroundPrimary.withValues(alpha: 0.55),
          border: null,
          largeTitle: Text(
            'Nooto',
            style: brandEmphasis(
              fontSize: 34,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          middle: Text(
            'Nooto',
            style: brandEmphasis(
              fontSize: 17,
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimary,
            ),
          ),
          trailing: const AppBarKebabMenu(),
        ),
        if (cards.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: _QuietEmpty(),
          )
        else
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppStyles.spacingL,
              AppStyles.spacingS,
              AppStyles.spacingL,
              AppStyles.spacingXL,
            ),
            sliver: SliverList.separated(
              itemCount: cards.length,
              separatorBuilder: (_, _) => const SizedBox(height: AppStyles.spacingL),
              itemBuilder: (context, i) => cards[i].render(context),
            ),
          ),
      ],
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
          style: brandEmphasis(
            fontSize: 18,
            fontWeight: FontWeight.w500,
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
