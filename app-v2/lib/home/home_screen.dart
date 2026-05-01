import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/companion_stream_provider.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/services/chat_service.dart';
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
        AppStyles.spacingS,
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

/// Tap-target composer that opens the Chat tab. NOT a real `TextField` —
/// the tap routes to chat via the [onTap] callback. Rectangular tile, no
/// chrome — the hint text + arrow do all the signalling.
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
          label: "What's on your mind. Opens chat.",
          child: Material(
            color: AppColors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
            child: InkWell(
              borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
              onTap: onTap,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppStyles.spacingL,
                  vertical: 14,
                ),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.06),
                  ),
                ),
                child: const Row(
                  children: [
                    Expanded(
                      child: Text(
                        "What's on your mind?",
                        style: TextStyle(
                          fontSize: 16,
                          color: AppColors.textTertiary,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    SizedBox(width: AppStyles.spacingS),
                    Icon(
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
