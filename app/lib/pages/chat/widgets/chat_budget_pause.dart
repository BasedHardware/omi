import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ChatBudgetPause extends StatefulWidget {
  const ChatBudgetPause({super.key});
  @override
  State<ChatBudgetPause> createState() => _ChatBudgetPauseState();
}

class _ChatBudgetPauseState extends State<ChatBudgetPause> with WidgetsBindingObserver {
  Timer? _timer;
  bool _loading = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load();
  }

  Future<void> _load() async {
    if (_loading || !mounted) return;
    _loading = true;
    try {
      if (!await PlanStorefrontGate.contextualEnabled() || !mounted) return;
      final owner = SharedPreferencesUtil().uid;
      final result = await PlanStorefrontApi()
          .load(source: 'mobile_chat', trigger: 'usage_budget', locale: context.l10n.localeName);
      if (mounted && owner == SharedPreferencesUtil().uid && result is ApiSuccess<PlanStorefront>) {
        context.read<MessageProvider>().applyChatAtCap(result.data.chatAtCap);
      }
    } finally {
      _loading = false;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<MessageProvider>().chatAtCap;
    if (state == null) return const SizedBox.shrink();
    return ChatPauseCard(
        state: state,
        onUpgrade: () async {
          await openContextualPlans(context, source: 'mobile_chat', trigger: 'usage_budget');
          await _load();
        });
  }
}

class ChatPauseCard extends StatelessWidget {
  const ChatPauseCard({super.key, required this.state, required this.onUpgrade});
  final ChatAtCap state;
  final VoidCallback onUpgrade;
  @override
  Widget build(BuildContext context) => Container(
        key: const Key('chat_budget_pause'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
            color: OmiColors.surface1, border: Border.all(color: OmiColors.border), borderRadius: OmiRadius.lgAll),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(state.title, style: OmiType.subhead),
          const SizedBox(height: OmiSpacing.sm),
          Text(state.body, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.sm),
          Text(state.resetLine, style: OmiType.footnote),
          if (state.upgradeLabel != null) ...[
            const SizedBox(height: OmiSpacing.md),
            OmiButton.secondary(label: state.upgradeLabel!, onPressed: onUpgrade),
          ],
        ]),
      );
}
