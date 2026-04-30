import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/chat_step_registry.dart';
import 'package:nooto_v2/companion/companion_turn.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/companion/widgets/chat_bubbles.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class OnboardingChatScreen extends StatefulWidget {
  const OnboardingChatScreen({super.key});

  @override
  State<OnboardingChatScreen> createState() => _OnboardingChatScreenState();
}

class _OnboardingChatScreenState extends State<OnboardingChatScreen> {
  final _scrollCtrl = ScrollController();
  final _textCtrl = TextEditingController();
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        context.read<OnboardingChatProvider>().bootstrap(context);
      });
    }
  }

  void _scrollToBottom() {
    if (!_scrollCtrl.hasClients) return;
    _scrollCtrl.animateTo(
      _scrollCtrl.position.maxScrollExtent,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
  }

  Future<void> _submit() async {
    final value = _textCtrl.text;
    if (value.trim().isEmpty) return;
    _textCtrl.clear();
    await context.read<OnboardingChatProvider>().submitTypedAnswer(context, value);
  }

  Future<void> _confirmReset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.backgroundSecondary,
        title: const Text('Reset onboarding?', style: TextStyle(color: AppColors.textPrimary)),
        content: const Text(
          'This wipes your saved chat state and starts over.',
          style: TextStyle(color: AppColors.textTertiary),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Reset', style: TextStyle(color: AppColors.errorColor)),
          ),
        ],
      ),
    );
    if (!mounted || ok != true) return;
    final provider = context.read<OnboardingChatProvider>();
    await provider.reset();
    if (!mounted) return;
    await provider.bootstrap(context);
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    _textCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        title: const _BrandStrip(),
        centerTitle: false,
        actions: kDebugMode
            ? [
                IconButton(
                  tooltip: 'Reset onboarding',
                  icon: const Icon(Icons.refresh, color: AppColors.textTertiary, size: 20),
                  onPressed: _confirmReset,
                ),
              ]
            : null,
      ),
      body: Consumer<OnboardingChatProvider>(
        builder: (context, provider, _) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
          final acceptsTyped = provider.acceptsTypedAnswer;
          final activeStep = provider.activeStep;
          return Column(
            children: [
              Expanded(
                child: ListView.builder(
                  controller: _scrollCtrl,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  itemCount: provider.messages.length,
                  itemBuilder: (context, i) {
                    final turn = provider.messages[i];
                    if (turn is AssistantTextTurn) return ChatBubbleAssistant(turn: turn);
                    if (turn is UserTextTurn) return ChatBubbleUser(turn: turn);
                    if (turn is WidgetTurn) {
                      final step = registryForCurrentPlatform()
                          .firstWhere((s) => s.id.name == turn.stepId, orElse: () => activeStep!);
                      if (turn.captured) return const SizedBox.shrink();
                      return step.widgetBuilder(context, turn.id);
                    }
                    return const SizedBox.shrink();
                  },
                ),
              ),
              SafeArea(
                top: false,
                child: Container(
                  decoration: const BoxDecoration(
                    color: AppColors.backgroundPrimary,
                    border: Border(top: BorderSide(color: Colors.white10, width: 1)),
                  ),
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _textCtrl,
                          enabled: acceptsTyped && !provider.isStreaming,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => _submit(),
                          minLines: 1,
                          maxLines: 4,
                          style: const TextStyle(color: AppColors.textPrimary, fontSize: 15),
                          decoration: InputDecoration(
                            hintText: acceptsTyped ? l.onboardingPromptHintTyped : l.onboardingPromptHintTap,
                            hintStyle: const TextStyle(color: AppColors.textTertiary, fontSize: 14),
                            filled: true,
                            fillColor: AppColors.backgroundSecondary,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
                              borderSide: BorderSide.none,
                            ),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      _SendButton(
                        enabled: acceptsTyped && !provider.isStreaming && _textCtrl.text.trim().isNotEmpty,
                        onTap: _submit,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _BrandStrip extends StatelessWidget {
  const _BrandStrip();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
              colors: [AppColors.brandLight, AppColors.brandPrimary, AppColors.brandAccent],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            boxShadow: [BoxShadow(color: AppColors.brandPrimary.withValues(alpha: 0.4), blurRadius: 14)],
          ),
        ),
        const SizedBox(width: 10),
        Text('Nooto', style: brandEmphasis(fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.textPrimary)),
      ],
    );
  }
}

class _SendButton extends StatelessWidget {
  final bool enabled;
  final VoidCallback onTap;
  const _SendButton({required this.enabled, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: enabled ? AppColors.brandPrimary : AppColors.backgroundTertiary,
      borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
        onTap: enabled ? onTap : null,
        child: const SizedBox(
          width: 44,
          height: 44,
          child: Icon(Icons.arrow_upward, color: Colors.white, size: 20),
        ),
      ),
    );
  }
}
