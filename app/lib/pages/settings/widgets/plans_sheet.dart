import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/gen/assets.gen.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../payment_webview_page.dart';

class PlansSheet extends StatefulWidget {
  final AnimationController waveController;
  final AnimationController notesController;
  final AnimationController arrowController;
  final Animation<double> arrowAnimation;
  final VoidCallback? onCancelSubscription;

  const PlansSheet({
    super.key,
    required this.waveController,
    required this.notesController,
    required this.arrowController,
    required this.arrowAnimation,
    this.onCancelSubscription,
  });

  @override
  State<PlansSheet> createState() => _PlansSheetState();
}

class _PlansSheetState extends State<PlansSheet> {
  String selectedPlan = 'yearly'; // 'yearly' or 'monthly'
  bool _isCancelling = false;
  bool _isUpgrading = false;
  bool _showTrainingDataOptIn = false; // Control visibility of training data opt-in

  Future<void> _loadAvailablePlans() async {
    final provider = context.read<UsageProvider>();
    await provider.loadAvailablePlans();
  }

  Future<void> _handleTrainingDataOptIn() async {
    // Show dialog with explanation and acknowledgement
    final acknowledged = await showDialog<bool>(
      context: context,
      builder: (ctx) => _buildTrainingDataDialog(ctx),
    );

    if (acknowledged != true) return;

    try {
      final userProvider = context.read<UserProvider>();
      await userProvider.optInForTrainingData();

      // Track the opt-in submission
      MixpanelManager().trainingDataOptInSubmitted();

      if (mounted) {
        AppSnackbar.showSnackbar(
          'Thank you! Your request is under review. We will notify you once approved.',
        );
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('An error occurred. Please try again.');
    }
  }

  Widget _buildTrainingDataDialog(BuildContext ctx) {
    bool isChecked = false;
    return StatefulBuilder(
      builder: (context, setDialogState) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1F1F25),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Text(
            'Omi Training',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Get Omi Unlimited for free by contributing your data to train AI models.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  '• Your data helps improve AI models\n'
                  '• Only non-sensitive data is shared\n'
                  '• Fully transparent process',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 16),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => Scaffold(
                          appBar: AppBar(
                            title: const Text('Training Data Program'),
                            backgroundColor: Colors.black,
                          ),
                          body: WebViewWidget(
                            controller: WebViewController()
                              ..setJavaScriptMode(JavaScriptMode.unrestricted)
                              ..loadRequest(Uri.parse('https://omi.me/training')),
                          ),
                        ),
                      ),
                    );
                  },
                  style: TextButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text(
                    'Learn more at omi.me/training',
                    style: TextStyle(
                      color: Colors.white,
                      decoration: TextDecoration.underline,
                      fontSize: 14,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                InkWell(
                  onTap: () {
                    setDialogState(() {
                      isChecked = !isChecked;
                    });
                  },
                  child: Row(
                    children: [
                      SizedBox(
                        width: 24,
                        height: 24,
                        child: Checkbox(
                          value: isChecked,
                          onChanged: (value) {
                            setDialogState(() {
                              isChecked = value ?? false;
                            });
                          },
                          fillColor: MaterialStateProperty.resolveWith((states) {
                            if (states.contains(MaterialState.selected)) {
                              return Colors.white;
                            }
                            return Colors.transparent;
                          }),
                          checkColor: Colors.black,
                          side: const BorderSide(color: Colors.white, width: 1.5),
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'I understand and agree to contribute my data for AI training',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.grey.shade400),
              ),
            ),
            TextButton(
              onPressed: isChecked ? () => Navigator.of(ctx).pop(true) : null,
              child: Text(
                'Submit Request',
                style: TextStyle(
                  color: isChecked ? Colors.white : Colors.grey.shade600,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _handleCancelSubscription() async {
    final provider = context.read<UsageProvider>();
    final sub = provider.subscription?.subscription;
    if (sub == null) return;

    String renewalDateInfo = 'at the end of your current billing period';
    if (sub.currentPeriodEnd != null) {
      final date = DateTime.fromMillisecondsSinceEpoch(sub.currentPeriodEnd! * 1000);
      renewalDateInfo = 'on ${DateFormat.yMMMd().format(date)}';
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => ConfirmationDialog(
        title: 'Cancel Subscription?',
        description:
            'Your plan will remain active until $renewalDateInfo. After that, you will lose access to your unlimited features. Are you sure?',
        confirmText: 'Confirm Cancellation',
        cancelText: 'Keep My Plan',
        onCancel: () => Navigator.of(ctx).pop(false),
        onConfirm: () => Navigator.of(ctx).pop(true),
      ),
    );

    if (confirmed != true) return;

    setState(() => _isCancelling = true);
    try {
      final provider = context.read<UsageProvider>();
      final success = await provider.cancelUserSubscription();
      if (success) {
        AppSnackbar.showSnackbar('Your subscription is set to cancel at the end of the period.');
      } else {
        AppSnackbar.showSnackbarError('Failed to cancel subscription. Please try again.');
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('An error occurred. Please try again.');
    } finally {
      if (mounted) {
        setState(() => _isCancelling = false);
      }
    }
  }

  Map<String, dynamic>? _getCurrentPlanDetails() {
    final provider = context.read<UsageProvider>();
    final availablePlans = provider.availablePlans;
    if (availablePlans == null) return null;

    final sub = provider.subscription?.subscription;
    if (sub == null || sub.stripeSubscriptionId?.isEmpty != false) return null;

    try {
      // Find the current plan in available plans based on is_active flag
      final plans = availablePlans['plans'] as List;
      final currentPlan = plans.firstWhere(
        (plan) => plan['is_active'] == true,
        orElse: () => null,
      );

      return currentPlan;
    } catch (e) {
      debugPrint('Error getting current plan details: $e');
      return null;
    }
  }

  bool _hasScheduledUpgrade() {
    final provider = context.read<UsageProvider>();
    final availablePlans = provider.availablePlans;
    if (availablePlans == null) return false;

    try {
      final plans = availablePlans['plans'] as List;
      final activePlans = plans.where((plan) => plan['is_active'] == true).toList();

      // If both monthly and annual plans are active, it means there's a scheduled upgrade
      if (activePlans.length == 2) {
        final intervals = activePlans.map((plan) => plan['interval'] as String).toSet();
        return intervals.contains('month') && intervals.contains('year');
      }

      return false;
    } catch (e) {
      debugPrint('Error checking scheduled upgrade: $e');
      return false;
    }
  }

  Map<String, dynamic>? _getScheduledPlanDetails() {
    final provider = context.read<UsageProvider>();
    final availablePlans = provider.availablePlans;
    if (availablePlans == null) return null;

    try {
      final plans = availablePlans['plans'] as List;
      // Find the annual plan if it's scheduled (both plans are active)
      final annualPlan = plans.firstWhere(
        (plan) => plan['is_active'] == true && plan['interval'] == 'year',
        orElse: () => null,
      );

      return annualPlan;
    } catch (e) {
      debugPrint('Error getting scheduled plan details: $e');
      return null;
    }
  }

  Future<void> _handleUpgradeWithSelectedPlan() async {
    final bool isYearly = selectedPlan == 'yearly';

    // Get the price ID from the available plans
    final usageProvider = context.read<UsageProvider>();
    final availablePlans = usageProvider.availablePlans;
    if (availablePlans == null) {
      AppSnackbar.showSnackbarError('Could not load available plans. Please try again.');
      return;
    }

    final plans = availablePlans['plans'] as List;
    final selectedPlanData = plans.firstWhere(
      (plan) => plan['interval'] == (isYearly ? 'year' : 'month'),
      orElse: () => null,
    );

    if (selectedPlanData == null) {
      AppSnackbar.showSnackbarError('Selected plan is not available. Please try again.');
      return;
    }

    final priceId = selectedPlanData['id'] as String;

    // Check if user is upgrading from monthly to annual
    final provider = context.read<UsageProvider>();
    final currentSub = provider.subscription?.subscription;
    final isUpgradingFromMonthlyToAnnual =
        currentSub?.plan == PlanType.unlimited && currentSub?.status == SubscriptionStatus.active && isYearly;

    if (isUpgradingFromMonthlyToAnnual && currentSub?.cancelAtPeriodEnd != true) {
      // Show confirmation popup for monthly to annual upgrade
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: const Color(0xFF1F1F25),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.payment, color: Colors.deepPurple, size: 24),
              SizedBox(width: 8),
              Text(
                'Upgrade to Annual Plan',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Important Billing Information:',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 12),
              _buildBillingInfoItem(
                icon: Icons.schedule,
                text: 'Your current monthly plan will continue until the end of your billing period',
              ),
              const SizedBox(height: 8),
              _buildBillingInfoItem(
                icon: Icons.credit_card,
                text: 'Your existing payment method will be charged automatically when your monthly plan ends',
              ),
              const SizedBox(height: 8),
              _buildBillingInfoItem(
                icon: Icons.calendar_today,
                text: 'Your 12-month annual subscription will start automatically after the charge',
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.deepPurple.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.deepPurple.withOpacity(0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, color: Colors.deepPurple, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'You\'ll get 13 months of coverage total (current month + 12 months annual)',
                        style: TextStyle(
                          color: Colors.deepPurple.shade300,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text(
                'Cancel',
                style: TextStyle(color: Colors.grey),
              ),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('Confirm Upgrade'),
            ),
          ],
        ),
      );

      if (confirmed != true) {
        return;
      }
    }

    MixpanelManager().upgradePlanSelected(plan: selectedPlan, source: 'Usage Page Plan Sheet');

    await _handleUpgrade(priceId);
  }

  Future<void> _handleUpgrade(String priceId) async {
    final provider = context.read<UsageProvider>();

    // Find the selected pricing option to show in the dialog.
    PricingOption? selectedPrice;
    final plans = provider.subscription?.availablePlans ?? [];
    for (final plan in plans) {
      for (final price in plan.prices) {
        if (price.id == priceId) {
          selectedPrice = price;
          break;
        }
      }
      if (selectedPrice != null) break;
    }

    if (selectedPrice == null) {
      AppSnackbar.showSnackbarError('Selected plan is not available. Please try again.');
      return;
    }

    final currentSub = provider.subscription!.subscription;

    if (currentSub.plan == PlanType.unlimited) {
      final description = "You're switching your Unlimited Plan to the ${selectedPrice.title}.";

      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => ConfirmationDialog(
          title: 'Confirm Plan Change',
          description: '$description Are you sure you want to proceed?',
          confirmText: 'Confirm & Proceed',
          cancelText: 'Cancel',
          onCancel: () => Navigator.of(ctx).pop(false),
          onConfirm: () => Navigator.of(ctx).pop(true),
        ),
      );

      if (confirmed != true) {
        return;
      }
    }

    setState(() => _isUpgrading = true);
    try {
      Map<String, dynamic>? result;

      // If user already has unlimited monthly plan and it's not canceled
      if (currentSub.plan == PlanType.unlimited &&
          currentSub.status == SubscriptionStatus.active &&
          !currentSub.cancelAtPeriodEnd) {
        result = await provider.upgradeUserSubscription(priceId: priceId);
        if (result != null) {
          final daysRemaining = result['days_remaining'] as int? ?? 0;
          AppSnackbar.showSnackbar(
              'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.');
        } else {
          AppSnackbar.showSnackbarError('Could not schedule plan change. Please try again.');
        }
      } else {
        // New subscription (for basic users or canceled subscriptions)
        final sessionData = await provider.createUserCheckoutSession(priceId: priceId);
        if (sessionData != null && mounted) {
          // Check if this was a reactivation
          if (sessionData.containsKey('status') && sessionData['status'] == 'reactivated') {
            // Quick reactivation - no charge now
            final message = sessionData['message'] as String? ??
                'Your subscription has been reactivated! No charge now - you\'ll be billed at the end of your current period.';
            AppSnackbar.showSnackbar(message);
            MixpanelManager().upgradeSucceeded();
            await provider.fetchSubscription();
          }
          // Otherwise, this is a new subscription requiring checkout
          else if (sessionData.containsKey('url') && sessionData['url'] != null) {
            final checkoutResult = await Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => PaymentWebViewPage(
                  checkoutUrl: sessionData['url']!,
                ),
              ),
            );

            if (checkoutResult == true) {
              AppSnackbar.showSnackbar('Subscription successful! You\'ve been charged for the new billing period.');
              MixpanelManager().upgradeSucceeded();
            } else {
              MixpanelManager().upgradeCancelled();
            }
          } else {
            AppSnackbar.showSnackbarError('Could not process subscription. Please try again.');
          }
        } else {
          AppSnackbar.showSnackbarError('Could not launch upgrade page. Please try again.');
        }
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('An error occurred. Please try again.');
    } finally {
      _loadAvailablePlans();
      if (mounted) setState(() => _isUpgrading = false);
    }
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadAvailablePlans();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UsageProvider>(builder: (context, provider, child) {
      final sub = provider.subscription?.subscription;
      final isUnlimited = sub?.plan == PlanType.unlimited;
      final isCancelled = sub?.cancelAtPeriodEnd ?? false;

      String renewalDate = 'N/A';
      if (sub?.currentPeriodEnd != null) {
        final date = DateTime.fromMillisecondsSinceEpoch(sub!.currentPeriodEnd! * 1000);
        renewalDate = DateFormat.yMMMd().format(date);
      }
      return DraggableScrollableSheet(
        initialChildSize: 0.9,
        minChildSize: 0.5,
        maxChildSize: 0.9,
        builder: (BuildContext context, ScrollController scrollController) {
          return Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  Colors.deepPurple.withOpacity(0.5),
                  Colors.deepPurple.withOpacity(0.3),
                  Colors.black.withOpacity(0.8),
                  Colors.black,
                ],
                stops: const [0.0, 0.2, 0.6, 1.0],
              ),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(20),
                topRight: Radius.circular(20),
              ),
            ),
            child: ListView(
              controller: scrollController,
              children: [
                Center(
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 24),
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.grey.shade700,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                SizedBox(
                  height: 150,
                  width: double.infinity,
                  child: Stack(
                    children: [
                      Row(
                        children: [
                          Expanded(
                            flex: 1,
                            child: ClipRect(
                              child: SizedBox(
                                height: 120,
                                child: AnimatedBuilder(
                                  animation: widget.waveController,
                                  builder: (context, child) {
                                    const double totalWidth = 420.0;
                                    final scrollOffset = (widget.waveController.value * totalWidth) % totalWidth;
                                    return Stack(
                                      children: [
                                        Positioned(
                                          left: -totalWidth + scrollOffset,
                                          top: 0,
                                          bottom: 0,
                                          child: Row(
                                            children: List.generate(60, (index) {
                                              final heights = [
                                                20.0,
                                                32.0,
                                                45.0,
                                                26.0,
                                                52.0,
                                                39.0,
                                                32.0,
                                                45.0,
                                                28.0,
                                                36.0,
                                                41.0,
                                                24.0,
                                                48.0,
                                                37.0,
                                                30.0,
                                                43.0,
                                                22.0,
                                                34.0,
                                                47.0,
                                                29.0,
                                                50.0,
                                                38.0,
                                                33.0,
                                                44.0
                                              ];
                                              final height = heights[index % heights.length];

                                              return Container(
                                                width: 4,
                                                height: height,
                                                margin: const EdgeInsets.symmetric(horizontal: 1.5),
                                                decoration: BoxDecoration(
                                                  color: Colors.red.withOpacity(0.7),
                                                  borderRadius: BorderRadius.circular(2),
                                                ),
                                              );
                                            }),
                                          ),
                                        ),
                                        Positioned(
                                          left: scrollOffset,
                                          top: 0,
                                          bottom: 0,
                                          child: Row(
                                            children: List.generate(60, (index) {
                                              final heights = [20.0, 32.0, 45.0, 26.0, 52.0, 39.0, 32.0, 45.0];
                                              final height = heights[index % heights.length];

                                              return Container(
                                                width: 4,
                                                height: height,
                                                margin: const EdgeInsets.symmetric(horizontal: 1.5),
                                                decoration: BoxDecoration(
                                                  color: Colors.red.withOpacity(0.7),
                                                  borderRadius: BorderRadius.circular(2),
                                                ),
                                              );
                                            }),
                                          ),
                                        ),
                                      ],
                                    );
                                  },
                                ),
                              ),
                            ),
                          ),
                          Expanded(
                            flex: 1,
                            child: ClipRect(
                              child: SizedBox(
                                height: 120,
                                child: AnimatedBuilder(
                                  animation: widget.notesController,
                                  builder: (context, child) {
                                    const double totalWidth = 440.0;
                                    final scrollOffset = (widget.notesController.value * totalWidth) % totalWidth;
                                    return Stack(
                                      children: [
                                        Positioned(
                                          left: -totalWidth + scrollOffset,
                                          top: 0,
                                          bottom: 0,
                                          child: Row(
                                            children: List.generate(8, (index) {
                                              return Container(
                                                width: 45,
                                                height: 55,
                                                margin: const EdgeInsets.symmetric(horizontal: 5),
                                                decoration: BoxDecoration(
                                                  color: Colors.white.withOpacity(0.95),
                                                  borderRadius: BorderRadius.circular(8),
                                                  boxShadow: [
                                                    BoxShadow(
                                                      color: Colors.black.withOpacity(0.15),
                                                      blurRadius: 4,
                                                      offset: const Offset(0, 2),
                                                    ),
                                                  ],
                                                ),
                                                child: Padding(
                                                  padding: const EdgeInsets.all(6),
                                                  child: Column(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      Container(
                                                        width: 26,
                                                        height: 3,
                                                        decoration: BoxDecoration(
                                                          color: Colors.black,
                                                          borderRadius: BorderRadius.circular(1.5),
                                                        ),
                                                      ),
                                                      const SizedBox(height: 4),
                                                      ...List.generate(
                                                          5,
                                                          (i) => Container(
                                                                width: i == 4 ? 24 : 35, // Last line shorter
                                                                height: 2,
                                                                margin: const EdgeInsets.symmetric(vertical: 2),
                                                                decoration: BoxDecoration(
                                                                  color: Colors.grey[350],
                                                                  borderRadius: BorderRadius.circular(1),
                                                                ),
                                                              )),
                                                    ],
                                                  ),
                                                ),
                                              );
                                            }),
                                          ),
                                        ),
                                        Positioned(
                                          left: scrollOffset,
                                          top: 0,
                                          bottom: 0,
                                          child: Row(
                                            children: List.generate(8, (index) {
                                              return Container(
                                                width: 45,
                                                height: 55,
                                                margin: const EdgeInsets.symmetric(horizontal: 5),
                                                decoration: BoxDecoration(
                                                  color: Colors.white.withOpacity(0.95),
                                                  borderRadius: BorderRadius.circular(8),
                                                  boxShadow: [
                                                    BoxShadow(
                                                      color: Colors.black.withOpacity(0.15),
                                                      blurRadius: 4,
                                                      offset: const Offset(0, 2),
                                                    ),
                                                  ],
                                                ),
                                                child: Padding(
                                                  padding: const EdgeInsets.all(6),
                                                  child: Column(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      Container(
                                                        width: 26,
                                                        height: 3,
                                                        decoration: BoxDecoration(
                                                          color: Colors.black,
                                                          borderRadius: BorderRadius.circular(1.5),
                                                        ),
                                                      ),
                                                      const SizedBox(height: 4),
                                                      ...List.generate(
                                                          5,
                                                          (i) => Container(
                                                                width: i == 4 ? 24 : 35, // Last line shorter
                                                                height: 2,
                                                                margin: const EdgeInsets.symmetric(vertical: 2),
                                                                decoration: BoxDecoration(
                                                                  color: Colors.grey[350],
                                                                  borderRadius: BorderRadius.circular(1),
                                                                ),
                                                              )),
                                                    ],
                                                  ),
                                                ),
                                              );
                                            }),
                                          ),
                                        ),
                                      ],
                                    );
                                  },
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                      Positioned(
                        left: (MediaQuery.of(context).size.width - 120) / 2,
                        top: 5,
                        child: Container(
                          width: 120,
                          height: 120,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.blue.withOpacity(0.4),
                                blurRadius: 20,
                                spreadRadius: 3,
                              ),
                            ],
                          ),
                          child: ClipOval(
                            child: Image.asset(
                              Assets.images.omiWithoutRope.path,
                              fit: BoxFit.cover,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    children: [
                      const SizedBox(height: 24),
                      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                        const FaIcon(FontAwesomeIcons.crown, color: Colors.yellow, size: 20),
                        const SizedBox(width: 8),
                        Builder(builder: (context) {
                          final hasScheduledUpgrade = _hasScheduledUpgrade();
                          if (hasScheduledUpgrade) {
                            return const Text(
                              'Upgrade Scheduled',
                              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                            );
                          } else {
                            return Text(
                              isUnlimited ? 'Change Plan' : 'Upgrade to Unlimited',
                              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                            );
                          }
                        }),
                      ]),
                      const SizedBox(height: 8),
                      Builder(builder: (context) {
                        final hasScheduledUpgrade = _hasScheduledUpgrade();
                        if (hasScheduledUpgrade) {
                          return Text(
                            'Your upgrade to the annual plan is already scheduled',
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                          );
                        } else {
                          return Text(
                            isUnlimited
                                ? 'You are on the Unlimited Plan.'
                                : 'Your Omi, unleashed. Go unlimited for endless possibilities.',
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                          );
                        }
                      }),
                      if (isUnlimited && isCancelled) ...[
                        const SizedBox(height: 8),
                        Builder(builder: (context) {
                          // Check if subscription period has ended
                          final sub = provider.subscription?.subscription;
                          final periodEnded = sub?.currentPeriodEnd != null &&
                              DateTime.fromMillisecondsSinceEpoch(sub!.currentPeriodEnd! * 1000)
                                  .isBefore(DateTime.now());

                          if (periodEnded) {
                            // Scenario B: Must create new subscription
                            return Text(
                              'Your plan ended on $renewalDate.\nResubscribe now - you\'ll be charged immediately for a new billing period.',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 14, color: Colors.orange.shade400),
                            );
                          } else {
                            // Scenario A: Can reactivate without charge
                            return Text(
                              'Your plan is set to cancel on $renewalDate.\nResubscribe now to keep your benefits - no charge until $renewalDate.',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 14, color: Colors.blue.shade400),
                            );
                          }
                        }),
                      ] else if (isUnlimited && !isCancelled) ...[
                        const SizedBox(height: 8),
                        Builder(builder: (context) {
                          final hasScheduledUpgrade = _hasScheduledUpgrade();
                          if (hasScheduledUpgrade) {
                            return Text(
                              'Your annual plan will start automatically when your monthly plan ends.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.deepPurple.shade400,
                                fontSize: 14,
                              ),
                            );
                          } else {
                            return Text(
                              'Your plan renews on $renewalDate.',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                            );
                          }
                        }),
                      ],
                      const SizedBox(height: 24),
                      // Features list
                      Column(
                        children: [
                          _buildFeatureItem(
                            faIcon: FontAwesomeIcons.infinity,
                            text: 'Unlimited conversations',
                          ),
                          const SizedBox(height: 16),
                          _buildFeatureItem(
                            faIcon: FontAwesomeIcons.solidComments,
                            text: 'Ask Omi anything about your life',
                          ),
                          const SizedBox(height: 16),
                          _buildFeatureItem(
                            faIcon: FontAwesomeIcons.brain,
                            text: 'Unlock Omi\'s infinite memory',
                          ),
                        ],
                      ),
                      const SizedBox(height: 32),

                      // Freemium plan option for basic users
                      if (!isUnlimited) ...[
                        _buildFreemiumPlanOption(isCurrentPlan: true),
                        const SizedBox(height: 18),
                      ],

                      // Training Data Opt-in Option - only show after plans are loaded
                      Consumer2<UsageProvider, UserProvider>(
                        builder: (context, usageProvider, userProvider, child) {
                          final shouldShowTrainingOption = _showTrainingDataOptIn &&
                              !usageProvider.isLoadingPlans &&
                              usageProvider.availablePlans != null;

                          if (!shouldShowTrainingOption) {
                            return const SizedBox.shrink();
                          }

                          final optedIn = userProvider.trainingDataOptedIn;
                          final status = userProvider.trainingDataStatus;
                          final isLoading = userProvider.isLoading;

                          return Container(
                            margin: const EdgeInsets.only(top: 24, bottom: 18),
                            child: _buildTrainingDataOption(
                              optedIn: optedIn,
                              status: status,
                              isLoading: isLoading,
                            ),
                          );
                        },
                      ),

                      // Check if user is on annual plan
                      if (isUnlimited && !isCancelled) ...[
                        // Get current plan details to check if it's annual
                        Builder(builder: (context) {
                          final currentPlan = _getCurrentPlanDetails();
                          final isOnAnnualPlan = currentPlan?['interval'] == 'year';
                          final hasScheduledUpgrade = _hasScheduledUpgrade();
                          final scheduledPlan = _getScheduledPlanDetails();

                          if (hasScheduledUpgrade) {
                            // User has a scheduled upgrade - show upgrade info
                            return Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.deepPurple.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(color: Colors.deepPurple.withOpacity(0.3)),
                              ),
                              child: Column(
                                children: [
                                  const Icon(Icons.schedule, color: Colors.deepPurple, size: 32),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Upgrade Scheduled!',
                                    style: TextStyle(
                                      color: Colors.deepPurple.shade300,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    'Your annual plan will start automatically when your monthly plan ends.',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      color: Colors.deepPurple.shade400,
                                      fontSize: 14,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          } else if (isOnAnnualPlan) {
                            // User is on annual plan - only show cancel option
                            return Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.blue.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(color: Colors.blue.withOpacity(0.3)),
                              ),
                              child: Column(
                                children: [
                                  const Icon(Icons.check_circle_outline, color: Colors.blue, size: 32),
                                  const SizedBox(height: 8),
                                  Text(
                                    'You\'re on the Annual Plan',
                                    style: TextStyle(
                                      color: Colors.blue.shade300,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    'You already have the best value plan. No changes needed.',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      color: Colors.blue.shade400,
                                      fontSize: 14,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          } else {
                            // User is on monthly plan - show upgrade options
                            return Consumer<UsageProvider>(
                              builder: (context, usageProvider, child) {
                                return Column(
                                  children: [
                                    if (usageProvider.isLoadingPlans) ...[
                                      _buildShimmerPlanOption(),
                                      const SizedBox(height: 18),
                                      _buildShimmerPlanOption(),
                                    ] else if (usageProvider.availablePlans != null) ...[
                                      _buildDynamicPlanOption(
                                        isSelected: selectedPlan == 'yearly',
                                        planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                          (plan) => plan['interval'] == 'year',
                                        ),
                                        saveTag: '2 Months Free',
                                        isPopular: true,
                                        onTap: () {
                                          HapticFeedback.lightImpact();
                                          setState(() => selectedPlan = 'yearly');
                                        },
                                      ),
                                      const SizedBox(height: 18),
                                      _buildDynamicPlanOption(
                                        isSelected: selectedPlan == 'monthly',
                                        planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                          (plan) => plan['interval'] == 'month',
                                        ),
                                        onTap: () {
                                          HapticFeedback.lightImpact();
                                          setState(() => selectedPlan = 'monthly');
                                        },
                                      ),
                                    ] else ...[
                                      Container(
                                        padding: const EdgeInsets.all(20),
                                        decoration: BoxDecoration(
                                          color: Colors.red.withOpacity(0.1),
                                          borderRadius: BorderRadius.circular(16),
                                          border: Border.all(color: Colors.red.withOpacity(0.3)),
                                        ),
                                        child: Column(
                                          children: [
                                            const Icon(Icons.error_outline, color: Colors.red, size: 32),
                                            const SizedBox(height: 8),
                                            Text(
                                              'Unable to load plans',
                                              style: TextStyle(
                                                color: Colors.red.shade300,
                                                fontSize: 16,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              'Please check your connection and try again',
                                              textAlign: TextAlign.center,
                                              style: TextStyle(
                                                color: Colors.red.shade400,
                                                fontSize: 14,
                                              ),
                                            ),
                                            const SizedBox(height: 12),
                                            TextButton(
                                              onPressed: () {
                                                _loadAvailablePlans();
                                              },
                                              child: const Text(
                                                'Retry',
                                                style: TextStyle(color: Colors.red),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ],
                                );
                              },
                            );
                          }
                        }),
                      ] else if (isUnlimited && isCancelled) ...[
                        // User has canceled subscription - show available plans to resubscribe
                        Consumer<UsageProvider>(
                          builder: (context, usageProvider, child) {
                            return Column(
                              children: [
                                if (usageProvider.isLoadingPlans) ...[
                                  _buildShimmerPlanOption(),
                                  const SizedBox(height: 18),
                                  _buildShimmerPlanOption(),
                                ] else if (usageProvider.availablePlans != null) ...[
                                  _buildDynamicPlanOption(
                                    isSelected: selectedPlan == 'yearly',
                                    planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                      (plan) => plan['interval'] == 'year',
                                    ),
                                    saveTag: '2 Months Free',
                                    isPopular: true,
                                    onTap: () {
                                      HapticFeedback.lightImpact();
                                      setState(() => selectedPlan = 'yearly');
                                    },
                                  ),
                                  const SizedBox(height: 18),
                                  _buildDynamicPlanOption(
                                    isSelected: selectedPlan == 'monthly',
                                    planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                      (plan) => plan['interval'] == 'month',
                                    ),
                                    onTap: () {
                                      HapticFeedback.lightImpact();
                                      setState(() => selectedPlan = 'monthly');
                                    },
                                  ),
                                ] else ...[
                                  Container(
                                    padding: const EdgeInsets.all(20),
                                    decoration: BoxDecoration(
                                      color: Colors.red.withOpacity(0.1),
                                      borderRadius: BorderRadius.circular(16),
                                      border: Border.all(color: Colors.red.withOpacity(0.3)),
                                    ),
                                    child: Column(
                                      children: [
                                        const Icon(Icons.error_outline, color: Colors.red, size: 32),
                                        const SizedBox(height: 8),
                                        Text(
                                          'Unable to load plans',
                                          style: TextStyle(
                                            color: Colors.red.shade300,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          'Please check your connection and try again',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                            color: Colors.red.shade400,
                                            fontSize: 14,
                                          ),
                                        ),
                                        const SizedBox(height: 12),
                                        TextButton(
                                          onPressed: () {
                                            _loadAvailablePlans();
                                          },
                                          child: const Text(
                                            'Retry',
                                            style: TextStyle(color: Colors.red),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ],
                            );
                          },
                        ),
                      ] else if (!isUnlimited) ...[
                        // User is on basic plan - show upgrade options
                        Consumer<UsageProvider>(
                          builder: (context, usageProvider, child) {
                            return Column(
                              children: [
                                if (usageProvider.isLoadingPlans) ...[
                                  _buildShimmerPlanOption(),
                                  const SizedBox(height: 18),
                                  _buildShimmerPlanOption(),
                                ] else if (usageProvider.availablePlans != null) ...[
                                  _buildDynamicPlanOption(
                                    isSelected: selectedPlan == 'yearly',
                                    planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                      (plan) => plan['interval'] == 'year',
                                    ),
                                    saveTag: '2 Months Free',
                                    isPopular: true,
                                    onTap: () {
                                      HapticFeedback.lightImpact();
                                      setState(() => selectedPlan = 'yearly');
                                    },
                                  ),
                                  const SizedBox(height: 18),
                                  _buildDynamicPlanOption(
                                    isSelected: selectedPlan == 'monthly',
                                    planData: (usageProvider.availablePlans!['plans'] as List).firstWhere(
                                      (plan) => plan['interval'] == 'month',
                                    ),
                                    onTap: () {
                                      HapticFeedback.lightImpact();
                                      setState(() => selectedPlan = 'monthly');
                                    },
                                  ),
                                ] else ...[
                                  Container(
                                    padding: const EdgeInsets.all(20),
                                    decoration: BoxDecoration(
                                      color: Colors.red.withOpacity(0.1),
                                      borderRadius: BorderRadius.circular(16),
                                      border: Border.all(color: Colors.red.withOpacity(0.3)),
                                    ),
                                    child: Column(
                                      children: [
                                        const Icon(Icons.error_outline, color: Colors.red, size: 32),
                                        const SizedBox(height: 8),
                                        Text(
                                          'Unable to load plans',
                                          style: TextStyle(
                                            color: Colors.red.shade300,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          'Please check your connection and try again',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                            color: Colors.red.shade400,
                                            fontSize: 14,
                                          ),
                                        ),
                                        const SizedBox(height: 12),
                                        TextButton(
                                          onPressed: () {
                                            _loadAvailablePlans();
                                          },
                                          child: const Text(
                                            'Retry',
                                            style: TextStyle(color: Colors.red),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ],
                            );
                          },
                        ),
                      ],

                      const SizedBox(height: 24),

                      // Continue button - only show for non-annual unlimited users
                      Builder(builder: (context) {
                        final currentPlan = _getCurrentPlanDetails();
                        final isOnAnnualPlan = currentPlan?['interval'] == 'year';
                        final hasScheduledUpgrade = _hasScheduledUpgrade();
                        final usageProvider = context.read<UsageProvider>();
                        final shouldShowContinueButton = !isOnAnnualPlan &&
                            !hasScheduledUpgrade &&
                            !isCancelled &&
                            !usageProvider.isLoadingPlans &&
                            usageProvider.availablePlans != null;

                        if (!shouldShowContinueButton) {
                          return const SizedBox.shrink();
                        }

                        return SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: _isUpgrading
                                ? null
                                : () {
                                    HapticFeedback.mediumImpact();
                                    _handleUpgradeWithSelectedPlan();
                                  },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: _isUpgrading ? Colors.grey : Colors.white,
                              foregroundColor: _isUpgrading ? Colors.white : Colors.black,
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                if (_isUpgrading) ...[
                                  const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  ),
                                ] else ...[
                                  const Text(
                                    'Continue',
                                    style: TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  AnimatedBuilder(
                                    animation: widget.arrowAnimation,
                                    builder: (context, child) {
                                      return Transform.translate(
                                        offset: Offset(widget.arrowAnimation.value, 0),
                                        child: const Icon(Icons.arrow_forward, size: 20),
                                      );
                                    },
                                  ),
                                ],
                              ],
                            ),
                          ),
                        );
                      }),

                      // Continue button for canceled subscriptions
                      Builder(builder: (context) {
                        final usageProvider = context.read<UsageProvider>();
                        final shouldShowResubscribeButton =
                            isCancelled && !usageProvider.isLoadingPlans && usageProvider.availablePlans != null;

                        if (!shouldShowResubscribeButton) {
                          return const SizedBox.shrink();
                        }

                        return SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: _isUpgrading
                                ? null
                                : () {
                                    HapticFeedback.mediumImpact();
                                    _handleUpgradeWithSelectedPlan();
                                  },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: _isUpgrading ? Colors.grey : Colors.white,
                              foregroundColor: _isUpgrading ? Colors.white : Colors.black,
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                if (_isUpgrading) ...[
                                  const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  ),
                                ] else ...[
                                  const Text(
                                    'Resubscribe',
                                    style: TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  AnimatedBuilder(
                                    animation: widget.arrowAnimation,
                                    builder: (context, child) {
                                      return Transform.translate(
                                        offset: Offset(widget.arrowAnimation.value, 0),
                                        child: const Icon(Icons.arrow_forward, size: 20),
                                      );
                                    },
                                  ),
                                ],
                              ],
                            ),
                          ),
                        );
                      }),
                      const SizedBox(height: 16),
                      if (isUnlimited == true && !isCancelled) ...[
                        SizedBox(
                          width: double.infinity,
                          height: 50,
                          child: OutlinedButton.icon(
                            onPressed: () async {
                              final navigator = Navigator.of(context);
                              final provider = context.read<UsageProvider>();
                              final portalData = await provider.openCustomerPortal();
                              if (portalData != null && portalData['url'] != null && mounted) {
                                await navigator.push(
                                  MaterialPageRoute(
                                    builder: (context) => PaymentWebViewPage(
                                      checkoutUrl: portalData['url']!,
                                      title: "Manage Payment Method",
                                    ),
                                  ),
                                );
                              } else {
                                AppSnackbar.showSnackbarError('Could not open payment settings. Please try again.');
                              }
                            },
                            icon: const Icon(Icons.credit_card, size: 20),
                            label: const Text('Manage Payment Method'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: Colors.white,
                              side: const BorderSide(color: Colors.white, width: 1),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextButton(
                          onPressed: () {
                            _handleCancelSubscription();
                          },
                          child: const Text('Cancel Subscription', style: TextStyle(color: Colors.red, fontSize: 16)),
                        ),
                        const SizedBox(height: 8),
                      ],
                    ],
                  ),
                )
              ],
            ),
          );
        },
      );
    });
  }

  Widget _buildFeatureItem({required IconData faIcon, required String text}) {
    return Row(
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: Colors.white,
              width: 1,
            ),
          ),
          child: Center(
            child: FaIcon(
              faIcon,
              color: Colors.white,
              size: 16,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w400,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHardcodedPlanOption({
    required bool isSelected,
    required String title,
    required String? subtitle,
    required String monthlyPrice,
    required VoidCallback onTap,
    String? saveTag,
    bool isPopular = false,
    bool isActive = false,
    String? endsOnDate,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25), // Use conversation list background
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.transparent,
            width: 2,
          ),
        ),
        child: Column(
          children: [
            // Popular badge only at the top
            if (isPopular) ...[
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Text(
                      'POPULAR',
                      style: TextStyle(
                        color: Colors.black,
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
            ],
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: Colors.grey[400],
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ],
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      monthlyPrice,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (saveTag != null) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.green.shade800,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          saveTag,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                    ],
                    if (endsOnDate != null) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.red.shade800,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          'Ends on $endsOnDate',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                    ] else if (isActive) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.red.shade800,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Text(
                          'Active',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerPlanOption() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25), // Use conversation list background
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 2,
        ),
      ),
      child: Column(
        children: [
          // Popular badge only at the top
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Shimmer.fromColors(
                      baseColor: Colors.white.withOpacity(0.1),
                      highlightColor: Colors.white.withOpacity(0.3),
                      child: Container(
                        height: 18,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Shimmer.fromColors(
                      baseColor: Colors.white.withOpacity(0.1),
                      highlightColor: Colors.white.withOpacity(0.3),
                      child: Container(
                        height: 14,
                        width: 100,
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Shimmer.fromColors(
                    baseColor: Colors.white.withOpacity(0.1),
                    highlightColor: Colors.white.withOpacity(0.3),
                    child: Container(
                      height: 18,
                      width: 100,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Shimmer.fromColors(
                    baseColor: Colors.white.withOpacity(0.1),
                    highlightColor: Colors.white.withOpacity(0.3),
                    child: Container(
                      height: 14,
                      width: 60,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDynamicPlanOption({
    required bool isSelected,
    required Map<String, dynamic> planData,
    String? saveTag,
    bool isPopular = false,
    required VoidCallback onTap,
  }) {
    final title = '${planData['title']} Unlimited';
    final priceString = planData['price_string'] as String;
    final interval = planData['interval'] as String;
    final unitAmount = planData['unit_amount'] as int;
    final isActive = planData['is_active'] as bool? ?? false;
    final planPriceId = planData['id'] as String;

    // Check if subscription is canceled and get end date
    final provider = context.read<UsageProvider>();
    final sub = provider.subscription?.subscription;
    final isCancelled = sub?.cancelAtPeriodEnd ?? false;
    String? endsOnDate;

    // Only show "Ends on [date]" badge if:
    // 1. Subscription is canceled
    // 2. This plan's price_id matches the current subscription's price_id
    if (isCancelled && sub?.currentPeriodEnd != null && sub?.currentPriceId == planPriceId) {
      final date = DateTime.fromMillisecondsSinceEpoch(sub!.currentPeriodEnd! * 1000);
      endsOnDate = DateFormat.yMMMd().format(date);
    }

    return _buildHardcodedPlanOption(
      isSelected: isSelected,
      saveTag: saveTag,
      isPopular: isPopular,
      title: title,
      subtitle: interval == 'year' ? '12 months / \$${unitAmount / 100}' : null,
      monthlyPrice: priceString,
      onTap: isActive ? () {} : onTap,
      isActive: isActive && !isCancelled,
      endsOnDate: endsOnDate,
    );
  }

  Widget _buildFreemiumPlanOption({required bool isCurrentPlan}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isCurrentPlan ? Colors.white.withOpacity(0.3) : Colors.transparent,
          width: 2,
        ),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Free Plan',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    GestureDetector(
                      onTap: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (context) => const TranscriptionSettingsPage()),
                        );
                      },
                      child: Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: '1,200 premium mins + unlimited ',
                              style: TextStyle(
                                color: Colors.grey[400],
                                fontSize: 14,
                              ),
                            ),
                            TextSpan(
                              text: 'on-device',
                              style: TextStyle(
                                color: Colors.grey[300],
                                fontSize: 14,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text(
                    '\$0',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (isCurrentPlan) ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Text(
                        'Current',
                        style: TextStyle(
                          color: Colors.black,
                          fontSize: 9,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.3,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildBillingInfoItem({required IconData icon, required String text}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: Colors.green, size: 16),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTrainingDataOption({
    required bool optedIn,
    required String? status,
    required bool isLoading,
  }) {
    // Approved status - show as active
    if (optedIn && status == 'approved') {
      return GestureDetector(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => Scaffold(
                appBar: AppBar(
                  title: const Text('Omi Training'),
                  backgroundColor: Colors.black,
                ),
                body: WebViewWidget(
                  controller: WebViewController()
                    ..setJavaScriptMode(JavaScriptMode.unrestricted)
                    ..loadRequest(Uri.parse('https://omi.me/training')),
                ),
              ),
            ),
          );
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.transparent,
              width: 2,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Get Free Unlimited Access',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Training data program',
                      style: TextStyle(
                        color: Colors.grey[400],
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      'Active',
                      style: TextStyle(
                        color: Colors.black,
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.3,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Icon(
                    Icons.arrow_forward_ios,
                    color: Colors.white,
                    size: 16,
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }

    // Pending status - show with link to learn more
    if (optedIn && status == 'pending_review') {
      return GestureDetector(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => Scaffold(
                appBar: AppBar(
                  title: const Text('Omi Training'),
                  backgroundColor: Colors.black,
                ),
                body: WebViewWidget(
                  controller: WebViewController()
                    ..setJavaScriptMode(JavaScriptMode.unrestricted)
                    ..loadRequest(Uri.parse('https://omi.me/training')),
                ),
              ),
            ),
          );
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.transparent,
              width: 2,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Get Free Unlimited Access',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Your request is under review',
                      style: TextStyle(
                        color: Colors.grey[400],
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.arrow_forward_ios,
                color: Colors.white,
                size: 16,
              ),
            ],
          ),
        ),
      );
    }

    // Default state - not opted in yet
    return GestureDetector(
      onTap: isLoading ? null : _handleTrainingDataOptIn,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.transparent,
            width: 2,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Get Free Unlimited Access',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Share data for training',
                    style: TextStyle(
                      color: Colors.grey[400],
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
            if (isLoading)
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              )
            else
              const Icon(
                Icons.arrow_forward_ios,
                color: Colors.white,
                size: 16,
              ),
          ],
        ),
      ),
    );
  }
}
