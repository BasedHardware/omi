import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Shows the phone calls upsell bottom sheet.
Future<void> showPhoneCallsUpsell(BuildContext context) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => const _PhoneCallsUpsellSheet(),
  );
}

class _PhoneCallsUpsellSheet extends StatelessWidget {
  const _PhoneCallsUpsellSheet();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF111113),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Drag handle
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 32),

              // Hero: phone icon with purple-tinted glow
              Stack(
                alignment: Alignment.center,
                children: [
                  // Glow
                  Container(
                    width: 96,
                    height: 96,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                            color: const Color(0xFF7C3AED).withValues(alpha: 0.25), blurRadius: 48, spreadRadius: 8),
                      ],
                    ),
                  ),
                  // Icon circle with purple border
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: const Color(0xFF1A1A20),
                      border: Border.all(color: const Color(0xFF7C3AED).withValues(alpha: 0.4), width: 1.5),
                    ),
                    child: const Icon(Icons.phone_in_talk_rounded, color: Color(0xFFB794F6), size: 30),
                  ),
                ],
              ),
              const SizedBox(height: 24),

              // Title
              Text(
                context.l10n.phoneCallsUnlimitedOnly,
                style: const TextStyle(
                    fontSize: 24, fontWeight: FontWeight.w700, color: Colors.white, letterSpacing: -0.5),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),

              // Subtitle
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Text(
                  context.l10n.phoneCallsUpsellSubtitle,
                  style: const TextStyle(fontSize: 14, color: Color(0xFF8E8E93), height: 1.5),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 28),

              // Feature list — clean, minimal
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A20),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFF2A2A34), width: 0.5),
                ),
                child: Column(
                  children: [
                    _FeatureRow(icon: Icons.graphic_eq_rounded, text: context.l10n.phoneCallsUpsellFeature1),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Divider(color: Color(0xFF2A2A34), height: 1),
                    ),
                    _FeatureRow(icon: Icons.auto_awesome_outlined, text: context.l10n.phoneCallsUpsellFeature2),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Divider(color: Color(0xFF2A2A34), height: 1),
                    ),
                    _FeatureRow(icon: Icons.verified_user_outlined, text: context.l10n.phoneCallsUpsellFeature3),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Divider(color: Color(0xFF2A2A34), height: 1),
                    ),
                    _FeatureRow(icon: Icons.lock_outline_rounded, text: context.l10n.phoneCallsUpsellFeature4),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              // Upgrade button — white on dark
              GestureDetector(
                onTap: () {
                  HapticFeedback.mediumImpact();
                  Navigator.of(context).pop();
                  showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    backgroundColor: Colors.black,
                    builder: (_) => const _PlansSheetWrapper(),
                  );
                },
                child: Container(
                  width: double.infinity,
                  height: 52,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    context.l10n.phoneCallsUpgradeButton,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.black),
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Dismiss
              GestureDetector(
                onTap: () => Navigator.of(context).pop(),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    context.l10n.phoneCallsMaybeLater,
                    style: const TextStyle(fontSize: 14, color: Color(0xFF636366)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FeatureRow extends StatelessWidget {
  final IconData icon;
  final String text;

  const _FeatureRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: Colors.white, size: 20),
        const SizedBox(width: 14),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(fontSize: 14, color: Color(0xFFCCCCD0), height: 1.3),
          ),
        ),
      ],
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
  late AnimationController _arrowController;
  late AnimationController _notesController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
    _arrowController = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..repeat();
    _notesController = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
    _arrowAnimation = Tween<double>(begin: 0, end: 10).animate(
      CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    _notesController.dispose();
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
