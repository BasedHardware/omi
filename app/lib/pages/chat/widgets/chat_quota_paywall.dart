import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/models/chat_quota.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ChatQuotaPaywall extends StatelessWidget {
  final ChatUsageQuota quota;
  final UsageProvider usageProvider;

  const ChatQuotaPaywall({
    super.key,
    required this.quota,
    required this.usageProvider,
  });

  String _getResetTimeDisplay(BuildContext context) {
    if (quota.resetAt == null) return '';
    final resetDate = DateTime.fromMillisecondsSinceEpoch(quota.resetAt! * 1000);
    final now = DateTime.now();
    final diff = resetDate.difference(now);
    if (diff.inDays > 0) {
      return context.l10n.resetsInDays(diff.inDays);
    } else if (diff.inHours > 0) {
      return context.l10n.resetsInHours(diff.inHours);
    }
    return context.l10n.resetsSoon;
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.55,
      minChildSize: 0.4,
      maxChildSize: 0.7,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1A1A20),
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
          ),
          child: ListView(
            controller: scrollController,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade700,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              const Icon(Icons.chat_bubble_outline, color: Colors.deepPurple, size: 48),
              const SizedBox(height: 16),
              Text(
                context.l10n.chatLimitReachedTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                context.l10n.chatUsageDescription(
                  quota.unit == ChatQuotaUnit.costUsd ? '\$${quota.used.toStringAsFixed(2)}' : '${quota.used.toInt()}',
                  quota.limitDisplay,
                  quota.plan,
                ),
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey.shade400,
                  fontSize: 15,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                _getResetTimeDisplay(context),
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    Navigator.of(context).pop();
                    showModalBottomSheet(
                      context: context,
                      isScrollControlled: true,
                      backgroundColor: Colors.transparent,
                      builder: (_) => const _PlansSheetWrapper(),
                    );
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurple,
                    foregroundColor: Colors.white,
                    elevation: 0,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.rocket_launch, size: 20),
                      const SizedBox(width: 8),
                      Text(context.l10n.upgradePlan, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: Text(
                    context.l10n.maybeLater,
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 15),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PlansSheetWrapper extends StatefulWidget {
  const _PlansSheetWrapper();

  @override
  State<_PlansSheetWrapper> createState() => _PlansSheetWrapperState();
}

class _PlansSheetWrapperState extends State<_PlansSheetWrapper> with TickerProviderStateMixin {
  late AnimationController _waveController;
  late AnimationController _notesController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(duration: const Duration(seconds: 20), vsync: this)..repeat();
    _notesController = AnimationController(duration: const Duration(seconds: 25), vsync: this)..repeat();
    _arrowController = AnimationController(duration: const Duration(milliseconds: 1500), vsync: this)
      ..repeat(reverse: true);
    _arrowAnimation = Tween<double>(begin: 0, end: 8).animate(
      CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _waveController.dispose();
    _notesController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _notesController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
    );
  }
}
