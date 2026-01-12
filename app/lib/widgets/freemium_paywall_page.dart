import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

/// Full-screen paywall shown when premium minutes are running low
class FreemiumPaywallPage extends StatefulWidget {
  final int remainingSeconds;
  final bool isOnDeviceReady;

  const FreemiumPaywallPage({
    super.key,
    required this.remainingSeconds,
    required this.isOnDeviceReady,
  });

  @override
  State<FreemiumPaywallPage> createState() => _FreemiumPaywallPageState();
}

class _FreemiumPaywallPageState extends State<FreemiumPaywallPage> with TickerProviderStateMixin {
  String selectedPlan = 'yearly';
  bool _isSwitchingToFree = false;

  late AnimationController _waveController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();

    _waveController = AnimationController(
      duration: const Duration(milliseconds: 18000),
      vsync: this,
    )..repeat();

    _arrowController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    )..repeat(reverse: true);

    _arrowAnimation = Tween<double>(begin: 0, end: 3).animate(
      CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut),
    );

    MixpanelManager().track('Freemium Paywall Viewed', properties: {
      'remaining_minutes': (widget.remainingSeconds / 60).round(),
      'on_device_ready': widget.isOnDeviceReady,
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<UsageProvider>().loadAvailablePlans();
    });
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  String get _remainingTimeText {
    final minutes = (widget.remainingSeconds / 60).ceil();
    if (minutes <= 0) return 'No premium minutes left';
    if (minutes == 1) return '1 minute left';
    if (minutes < 60) return '$minutes mins left';
    final hours = (minutes / 60).round();
    return '$hours hr${hours > 1 ? 's' : ''} left';
  }

  bool get _isUrgent => (widget.remainingSeconds / 60) <= 10;

  Future<void> _handleUpgrade() async {
    HapticFeedback.mediumImpact();
    MixpanelManager().track('Freemium Paywall Upgrade Tapped', properties: {
      'selected_plan': selectedPlan,
    });

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      builder: (sheetContext) {
        return PlansSheet(
          waveController: _waveController,
          notesController: _waveController,
          arrowController: _arrowController,
          arrowAnimation: _arrowAnimation,
        );
      },
    );

    if (!mounted) return;
    final provider = context.read<UsageProvider>();
    await provider.fetchSubscription();
    if (!mounted) return;
    if (provider.subscription?.subscription.plan == PlanType.unlimited) {
      Navigator.of(context).pop(true);
    }
  }

  Future<void> _handleContinueWithFree() async {
    HapticFeedback.lightImpact();

    if (!widget.isOnDeviceReady) {
      MixpanelManager().track('Freemium Paywall Setup OnDevice Tapped');
      final result = await Navigator.of(context).push(
        MaterialPageRoute(builder: (context) => const TranscriptionSettingsPage()),
      );
      if (mounted && result == true) {
        Navigator.of(context).pop(false);
      }
      return;
    }

    setState(() => _isSwitchingToFree = true);

    try {
      MixpanelManager().track('Freemium Paywall OnDevice Selected');

      final freemiumService = FreemiumTranscriptionService();
      final config = freemiumService.getFreemiumConfig();

      if (config != null) {
        await SharedPreferencesUtil().saveCustomSttConfig(config);
        if (!mounted) return;
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        await captureProvider.onRecordProfileSettingChanged();
        if (!mounted) return;
        Navigator.of(context).pop(false);
      }
    } catch (e) {
      debugPrint('Error switching to on-device: $e');
    } finally {
      if (mounted) setState(() => _isSwitchingToFree = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const SizedBox(width: 48),
                  _buildTimeBadge(),
                  IconButton(
                    onPressed: () {
                      MixpanelManager().track('Freemium Paywall Dismissed');
                      Navigator.of(context).pop();
                    },
                    icon: Icon(Icons.close, color: Colors.grey.shade600, size: 24),
                  ),
                ],
              ),
            ),

            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    const SizedBox(height: 16),
                    _buildHeroSection(),
                    const SizedBox(height: 32),
                    _buildPremiumBenefits(),
                    const SizedBox(height: 32),
                    _buildUpgradeButton(),
                    const SizedBox(height: 16),
                    _buildFreeOption(),
                    const SizedBox(height: 32),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTimeBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: _isUrgent ? Colors.red.withValues(alpha: 0.15) : Colors.grey.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.schedule,
            color: _isUrgent ? Colors.red.shade300 : Colors.grey.shade400,
            size: 14,
          ),
          const SizedBox(width: 6),
          Text(
            _remainingTimeText,
            style: TextStyle(
              color: _isUrgent ? Colors.red.shade300 : Colors.grey.shade400,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeroSection() {
    return Column(
      children: [
        const Icon(
          FontAwesomeIcons.crown,
          color: Colors.amber,
          size: 48,
        ),
        const SizedBox(height: 20),
        const Text(
          'Go Unlimited',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.white,
            fontSize: 32,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Never worry about minutes again',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.grey.shade500,
            fontSize: 16,
          ),
        ),
      ],
    );
  }

  Widget _buildPremiumBenefits() {
    return Column(
      children: [
        _buildBenefitRow(Icons.all_inclusive, 'Unlimited transcription'),
        const SizedBox(height: 16),
        _buildBenefitRow(Icons.bolt, 'Fastest & most accurate'),
        const SizedBox(height: 16),
        _buildBenefitRow(Icons.people_outline, 'Speaker detection'),
        const SizedBox(height: 16),
        _buildBenefitRow(Icons.psychology_outlined, 'Unlimited AI memory'),
        const SizedBox(height: 24),
        _buildComparisonTable(),
      ],
    );
  }

  Widget _buildBenefitRow(IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, color: Colors.white, size: 22),
        const SizedBox(width: 14),
        Text(
          text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }

  Widget _buildComparisonTable() {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            child: Row(
              children: [
                const Expanded(flex: 2, child: SizedBox()),
                Expanded(
                  child: Text(
                    'Premium',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.deepPurple.shade300,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                Expanded(
                  child: Text(
                    'On-Device',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
          _buildComparisonRow('Speed', 'Instant', 'Slower', true),
          _buildComparisonRow('Accuracy', 'Best', '6/10', true),
          _buildComparisonRow('Speaker ID', '✓', '✗', true),
          _buildComparisonRow('Battery', 'Low', '30%/hour', true),
          _buildComparisonRow('Offline', '✗', '✓', false),
          _buildComparisonRow('Price', 'Paid', 'Free', false, isLast: true),
        ],
      ),
    );
  }

  Widget _buildComparisonRow(String feature, String premium, String free, bool premiumBetter, {bool isLast = false}) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      decoration: BoxDecoration(
        border: isLast ? null : Border(bottom: BorderSide(color: Colors.grey.shade800, width: 0.5)),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(
              feature,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            ),
          ),
          Expanded(
            child: Text(
              premium,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: premiumBetter ? Colors.green.shade400 : Colors.grey.shade500,
                fontSize: 12,
                fontWeight: premiumBetter ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ),
          Expanded(
            child: Text(
              free,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: !premiumBetter ? Colors.green.shade400 : Colors.grey.shade500,
                fontSize: 12,
                fontWeight: !premiumBetter ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPlanSelector() {
    return Consumer<UsageProvider>(
      builder: (context, provider, child) {
        if (provider.isLoadingPlans) {
          return const SizedBox(
            height: 80,
            child: Center(
              child: SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white24,
                ),
              ),
            ),
          );
        }

        final plans = provider.availablePlans?['plans'] as List?;
        if (plans == null) return const SizedBox.shrink();

        return Row(
          children: [
            Expanded(
              child: _buildPlanOption(
                isSelected: selectedPlan == 'yearly',
                title: 'Annual',
                price: _getPlanPrice(plans, 'year'),
                badge: 'Best Value',
                onTap: () => setState(() => selectedPlan = 'yearly'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildPlanOption(
                isSelected: selectedPlan == 'monthly',
                title: 'Monthly',
                price: _getPlanPrice(plans, 'month'),
                onTap: () => setState(() => selectedPlan = 'monthly'),
              ),
            ),
          ],
        );
      },
    );
  }

  String _getPlanPrice(List plans, String interval) {
    try {
      final plan = plans.firstWhere((p) => p['interval'] == interval);
      return plan['price_string'] ?? '';
    } catch (_) {
      return '';
    }
  }

  Widget _buildPlanOption({
    required bool isSelected,
    required String title,
    required String price,
    String? badge,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF1F1F25) : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.grey.shade800,
            width: 1.5,
          ),
        ),
        child: Column(
          children: [
            if (badge != null) ...[
              Text(
                badge,
                style: TextStyle(
                  color: Colors.green.shade400,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
            ],
            Text(
              title,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.grey.shade500,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              price,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.grey.shade400,
                fontSize: 17,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUpgradeButton() {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: _handleUpgrade,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              'Continue',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(width: 6),
            AnimatedBuilder(
              animation: _arrowAnimation,
              builder: (context, child) {
                return Transform.translate(
                  offset: Offset(_arrowAnimation.value, 0),
                  child: const Icon(Icons.arrow_forward, size: 18),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFreeOption() {
    final buttonText = widget.isOnDeviceReady ? 'Use on-device instead (free)' : 'Setup free on-device option';

    return TextButton(
      onPressed: _isSwitchingToFree ? null : _handleContinueWithFree,
      child: _isSwitchingToFree
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.grey),
            )
          : Text(
              buttonText,
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 14,
              ),
            ),
    );
  }
}
