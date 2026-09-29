import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Goals, opened from Settings. They used to sit at the top of the Conversations tab, which no
/// longer exists: Home shows only recaps and conversations.
class GoalsPage extends StatefulWidget {
  const GoalsPage({super.key});

  @override
  State<GoalsPage> createState() => _GoalsPageState();
}

class _GoalsPageState extends State<GoalsPage> {
  final GlobalKey<GoalsWidgetState> _goalsKey = GlobalKey<GoalsWidgetState>();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<GoalsProvider>().refresh();
    });
  }

  @override
  Widget build(BuildContext context) {
    final goals = context.watch<GoalsProvider>();
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: RefreshIndicator(
        onRefresh: () => context.read<GoalsProvider>().refresh(),
        child: ListView(
          padding: const EdgeInsets.only(bottom: OmiSpacing.xl),
          children: [
            GoalsWidget(key: _goalsKey),
            if (!goals.isLoading && goals.goals.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 120),
                child: OmiEmptyState(
                  icon: Icons.flag_outlined,
                  title: context.l10n.goals,
                  action: OmiButton.secondary(
                    label: context.l10n.addGoal,
                    onPressed: () => _goalsKey.currentState?.addGoal(),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
