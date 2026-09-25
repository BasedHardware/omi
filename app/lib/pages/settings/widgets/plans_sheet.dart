import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/pages/settings/widgets/plans/plans_hero.dart';
import 'package:omi/pages/settings/widgets/plans/training_data_option.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/plan_pricing.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';

/// Plan picker, upgrade/downgrade and payment management.
///
/// Content for a bottom sheet: present it with `showOmiSheet(context: context, padding:
/// EdgeInsets.zero, builder: (_) => PlansSheet(...))`, which draws the handle, close button and
/// sheet surface.
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
  String selectedPlan = 'yearly'; // 'yearly' or 'monthly'  (billing period)
  String? selectedTierId; // 'unlimited', 'operator', 'architect'
  bool _isUpgrading = false;
  final bool _showTrainingDataOptIn = false; // Control visibility of training data opt-in
  bool _isSwitchingToFree = false;
  final _promoCodeController = TextEditingController();
  String? _promoCodeError;
  bool _showPromoCodeField = false;

  Future<void> _loadAvailablePlans() async {
    final provider = context.read<UsageProvider>();
    await provider.loadAvailablePlans();
  }

  Future<void> _handleTrainingDataOptIn() async {
    final userProvider = context.read<UserProvider>();
    final l10n = context.l10n;
    // Explain the program and ask for an explicit agreement first.
    if (!await showTrainingDataOptInDialog(context)) return;

    try {
      await userProvider.optInForTrainingData();

      // Track the opt-in submission
      PlatformManager.instance.analytics.trainingDataOptInSubmitted();

      if (mounted) OmiFeedback.confirm(context, l10n.thankYouRequestUnderReview);
    } catch (e) {
      if (mounted) OmiFeedback.error(context, l10n.anErrorOccurredTryAgain);
    }
  }

  Future<void> _handleCancelSubscription() async {
    await CancelSubscriptionFlow.show(context);
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
      final currentPlan = plans.firstWhere((plan) => plan['is_active'] == true, orElse: () => null);

      return currentPlan;
    } catch (e) {
      Logger.debug('Error getting current plan details: $e');
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
      Logger.debug('Error checking scheduled upgrade: $e');
      return false;
    }
  }

  Future<void> _handleSwitchToFreePlan() async {
    setState(() => _isSwitchingToFree = true);

    try {
      PlatformManager.instance.analytics.track('Free Plan Selected', properties: {'source': 'plans_sheet'});

      final freemiumService = FreemiumTranscriptionService();
      final readiness = await freemiumService.checkReadiness();

      if (readiness == FreemiumReadiness.ready) {
        final config = freemiumService.getFreemiumConfig();
        if (config != null) {
          await SharedPreferencesUtil().saveCustomSttConfig(config);
          if (!mounted) return;

          final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
          await captureProvider.onRecordProfileSettingChanged();

          if (!mounted) return;
          OmiFeedback.confirm(context, context.l10n.switchedToOnDevice);
          Navigator.of(context).pop(false); // false = switched to free
        }
      } else {
        // Need to set up on-device first
        if (!mounted) return;
        Navigator.of(context).pop();
        routeToPage(context, const TranscriptionSettingsPage());
      }
    } catch (e) {
      Logger.debug('Error switching to free plan: $e');
      if (mounted) OmiFeedback.error(context, context.l10n.couldNotSwitchToFreePlan);
    } finally {
      if (mounted) setState(() => _isSwitchingToFree = false);
    }
  }

  Future<void> _handleDowngradeToFreemium() async {
    // Confirm with the limitations the reader will get.
    final l10n = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => OmiAlertDialog(
        title: l10n.downgradeToFreemiumTitle,
        content: Material(
          type: MaterialType.transparency,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.downgradeLimitationsHeading, textAlign: TextAlign.start, style: OmiType.subhead),
              const SizedBox(height: OmiSpacing.xs),
              PlanDialogLine(
                  icon: FontAwesomeIcons.carBattery, text: l10n.downgradeLimitBattery, color: OmiColors.danger),
              PlanDialogLine(
                icon: FontAwesomeIcons.triangleExclamation,
                text: l10n.downgradeLimitQuality,
                color: OmiColors.danger,
              ),
              PlanDialogLine(icon: FontAwesomeIcons.clock, text: l10n.downgradeLimitDelay, color: OmiColors.danger),
              PlanDialogLine(
                  icon: FontAwesomeIcons.userSlash, text: l10n.downgradeLimitSpeakers, color: OmiColors.danger),
            ],
          ),
        ),
        actions: [
          OmiDialogAction(label: l10n.cancel, isDefault: true, onPressed: () => Navigator.of(ctx).pop(false)),
          OmiDialogAction(
              label: l10n.downgradeAnyway, isDestructive: true, onPressed: () => Navigator.of(ctx).pop(true)),
        ],
      ),
    );

    if (confirmed != true) return;

    await _handleSwitchToFreePlan();
  }

  Future<void> _handleUpgradeWithSelectedPlan() async {
    final bool isYearly = selectedPlan == 'yearly';

    // Get the price ID from the available plans
    final usageProvider = context.read<UsageProvider>();
    final availablePlans = usageProvider.availablePlans;
    if (availablePlans == null) {
      OmiFeedback.error(context, context.l10n.couldNotLoadPlans);
      return;
    }

    final plans = availablePlans['plans'] as List;
    final tierId = selectedTierId;

    // Find the matching plan: match tier + billing period
    Map<String, dynamic>? selectedPlanData;
    if (tierId != null) {
      selectedPlanData = plans.cast<Map<String, dynamic>>().firstWhereOrNull(
            (plan) => plan['plan_id'] == tierId && plan['interval'] == (isYearly ? 'year' : 'month'),
          );
    }
    // Fallback to old behavior (first plan matching interval) for backwards compat
    selectedPlanData ??= plans.cast<Map<String, dynamic>>().firstWhereOrNull(
          (plan) => plan['interval'] == (isYearly ? 'year' : 'month'),
        );

    if (selectedPlanData == null) {
      OmiFeedback.error(context, context.l10n.selectedPlanNotAvailable);
      return;
    }

    final priceId = selectedPlanData['id'] as String;

    // Check if user is upgrading from monthly to annual
    final provider = context.read<UsageProvider>();
    final currentSub = provider.subscription?.subscription;
    if (currentSub?.cancelAtPeriodEnd == true && priceId != currentSub?.currentPriceId) {
      return;
    }
    // Only show "no charge until renewal" dialog for same-tier monthly→annual switch.
    // Cross-tier changes are immediate+prorated on the backend, not deferred.
    final currentTierName = currentSub?.plan.wireName; // backend plan_id, e.g. 'plus', 'unlimited_v2'
    final isSameTier = currentTierName == tierId;
    final isUpgradingFromMonthlyToAnnual =
        isSameTier && (currentSub?.plan.isPaid ?? false) && currentSub?.status == SubscriptionStatus.active && isYearly;

    if (isUpgradingFromMonthlyToAnnual && currentSub?.cancelAtPeriodEnd != true) {
      final l10n = context.l10n;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => OmiAlertDialog(
          title: l10n.upgradeToAnnualPlan,
          content: Material(
            type: MaterialType.transparency,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l10n.importantBillingInfo,
                  textAlign: TextAlign.start,
                  style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: OmiSpacing.xxs),
                PlanDialogLine(icon: FontAwesomeIcons.clock, text: l10n.monthlyPlanContinues),
                PlanDialogLine(icon: FontAwesomeIcons.creditCard, text: l10n.paymentMethodCharged),
                PlanDialogLine(icon: FontAwesomeIcons.calendarDay, text: l10n.annualSubscriptionStarts),
                const SizedBox(height: OmiSpacing.xs),
                PlanDialogLine(
                  icon: FontAwesomeIcons.circleInfo,
                  text: l10n.thirteenMonthsCoverage,
                  color: OmiColors.success,
                ),
              ],
            ),
          ),
          actions: [
            OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.of(ctx).pop(false)),
            OmiDialogAction(label: l10n.confirmUpgrade, isDefault: true, onPressed: () => Navigator.of(ctx).pop(true)),
          ],
        ),
      );

      if (confirmed != true) {
        return;
      }
    }

    PlatformManager.instance.analytics.upgradePlanSelected(plan: selectedPlan, source: 'Usage Page Plan Sheet');

    await _handleUpgrade(priceId, targetPlan: tierId ?? 'unknown', billingInterval: isYearly ? 'year' : 'month');
  }

  Future<void> _handleUpgrade(String priceId, {required String targetPlan, required String billingInterval}) async {
    final provider = context.read<UsageProvider>();
    final l10n = context.l10n;

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
      OmiFeedback.error(context, l10n.selectedPlanNotAvailable);
      return;
    }

    final currentSub = provider.subscription!.subscription;

    if (currentSub.plan.isPaid) {
      final confirmed = await showOmiConfirm(
        context,
        title: l10n.confirmPlanChange,
        message: l10n.planSwitchingDescriptionWithTitle(selectedPrice.title),
        confirmLabel: l10n.changePlan,
      );
      if (!confirmed) return;
    }

    setState(() => _isUpgrading = true);
    final promoCode = _promoCodeController.text.trim();
    try {
      Map<String, dynamic>? result;

      // If user already has a paid plan and it's not canceled
      if (currentSub.plan.isPaid && currentSub.status == SubscriptionStatus.active && !currentSub.cancelAtPeriodEnd) {
        result = await provider.upgradeUserSubscription(
          priceId: priceId,
          promotionCode: promoCode.isNotEmpty ? promoCode : null,
        );
        if (result != null && result['error'] == true) {
          final detail = result['detail'] as String? ?? l10n.invalidPromotionCode;
          if (promoCode.isNotEmpty) {
            setState(() => _promoCodeError = detail);
          } else {
            if (mounted) OmiFeedback.error(context, detail);
          }
          return;
        } else if (result != null) {
          setState(() => _promoCodeError = null);
          _promoCodeController.clear();
          if (mounted) OmiFeedback.confirm(context, l10n.planUpgradeScheduledMessage);
        } else {
          if (mounted) OmiFeedback.error(context, l10n.couldNotSchedulePlanChange);
        }
      } else {
        // New subscription (for basic users or canceled subscriptions)
        final sessionData = await provider.createUserCheckoutSession(
          priceId: priceId,
          promotionCode: promoCode.isNotEmpty ? promoCode : null,
        );
        if (sessionData != null && mounted) {
          // Check if this was a reactivation
          if (sessionData.containsKey('status') && sessionData['status'] == 'reactivated') {
            // Quick reactivation - no charge now
            final message = sessionData['message'] as String? ?? l10n.subscriptionReactivatedDefault;
            if (mounted) OmiFeedback.confirm(context, message);
            PlatformManager.instance.analytics.upgradeSucceeded(
              previousPlan: currentSub.plan.wireName,
              newPlan: targetPlan,
              billingInterval: billingInterval,
            );
            await provider.fetchSubscription();
          }
          // Otherwise, this is a new subscription requiring checkout
          else if (sessionData.containsKey('url') && sessionData['url'] != null) {
            final checkoutResult = await routeToPage(context, PaymentWebViewPage(checkoutUrl: sessionData['url']!));

            if (checkoutResult == true) {
              if (mounted) OmiFeedback.confirm(context, l10n.subscriptionSuccessfulCharged);
              PlatformManager.instance.analytics.upgradeSucceeded(
                previousPlan: currentSub.plan.wireName,
                newPlan: targetPlan,
                billingInterval: billingInterval,
              );
            } else {
              PlatformManager.instance.analytics.upgradeCancelled();
            }
          } else {
            if (mounted) OmiFeedback.error(context, l10n.couldNotProcessSubscription);
          }
        } else {
          if (mounted) OmiFeedback.error(context, l10n.couldNotLaunchUpgradePage);
        }
      }
    } catch (e) {
      if (mounted) OmiFeedback.error(context, l10n.anErrorOccurredTryAgain);
    } finally {
      _loadAvailablePlans();
      if (mounted) setState(() => _isUpgrading = false);
    }
  }

  Future<void> _openPaymentPortal() async {
    final navigator = Navigator.of(context);
    final provider = context.read<UsageProvider>();
    final l10n = context.l10n;
    final portalData = await provider.openCustomerPortal();
    if (portalData != null && portalData['url'] != null && mounted) {
      await navigator.push(
        omiPageRoute(
          builder: (context) => PaymentWebViewPage(checkoutUrl: portalData['url']!, title: l10n.managePaymentMethod),
        ),
      );
      // The user may have paid an overdue invoice or recovered a canceled plan inside the portal,
      // so refresh subscription state on return instead of leaving the UI showing Free until a
      // manual reload.
      await provider.fetchSubscription();
      await provider.loadAvailablePlans();
    } else if (mounted) {
      OmiFeedback.error(context, l10n.couldNotOpenPaymentSettings);
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
  void dispose() {
    _promoCodeController.dispose();
    super.dispose();
  }

  /// Plan cards, their loading placeholder, or the failure state with Try Again.
  Widget _plansOrPlaceholder(UsageProvider usageProvider) {
    if (usageProvider.isLoadingPlans) {
      return const Column(
        children: [PlanOptionShimmer(), SizedBox(height: 18), PlanOptionShimmer()],
      );
    }
    if (usageProvider.availablePlans != null) {
      return _buildTierPlanCards(availablePlans: usageProvider.availablePlans!);
    }
    return OmiErrorState(
      title: context.l10n.unableToLoadPlans,
      message: context.l10n.checkConnectionTryAgain,
      onRetry: _loadAvailablePlans,
    );
  }

  /// The main action: Upgrade, Continue or Resubscribe.
  Widget _primaryAction({Key? key, required String label}) {
    return OmiButton(
      key: key,
      label: label,
      expand: true,
      isLoading: _isUpgrading,
      onPressed: () {
        HapticFeedback.mediumImpact();
        return _handleUpgradeWithSelectedPlan();
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UsageProvider>(
      builder: (context, provider, child) {
        // Pop on build if the server-driven visibility flag is off, in case any
        // caller bypassed the call-site check.
        if (!provider.showSubscriptionUI) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (Navigator.of(context).canPop()) Navigator.of(context).pop();
          });
          return const SizedBox.shrink();
        }

        final l10n = context.l10n;
        final sub = provider.subscription?.subscription;
        final isPaidPlan = sub?.plan.isPaid ?? false;
        final isUnlimited = isPaidPlan; // backward-compat alias for UI branching
        final isCancelled = sub?.cancelAtPeriodEnd ?? false;
        final hasScheduledUpgrade = _hasScheduledUpgrade();
        final plansLoaded = !provider.isLoadingPlans && provider.availablePlans != null;

        String renewalDate = '—';
        final periodEnd = sub?.currentPeriodEnd;
        if (periodEnd != null) {
          renewalDate = OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(periodEnd * 1000));
        }
        final periodEnded =
            periodEnd != null && DateTime.fromMillisecondsSinceEpoch(periodEnd * 1000).isBefore(DateTime.now());
        final secondary = OmiType.subhead.copyWith(color: OmiColors.textSecondary);

        return DecoratedBox(
          // Paints the sheet surface itself too, for hosts that present it without showOmiSheet.
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.sheetTop),
          child: SizedBox(
            height: MediaQuery.sizeOf(context).height * 0.85,
            child: ListView(
              padding: const EdgeInsets.only(bottom: OmiSpacing.md),
              children: [
                const SizedBox(height: OmiSpacing.xs),
                PlansHero(waveController: widget.waveController, notesController: widget.notesController),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
                  child: Column(
                    children: [
                      const SizedBox(height: OmiSpacing.xl),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const ExcludeSemantics(child: FaIcon(FontAwesomeIcons.crown, color: Colors.amber, size: 20)),
                          const SizedBox(width: OmiSpacing.xs),
                          Flexible(
                            child: Semantics(
                              header: true,
                              child: Text(
                                hasScheduledUpgrade
                                    ? l10n.upgradeScheduled
                                    : (isUnlimited ? l10n.changePlan : l10n.upgradeYourPlan),
                                style: OmiType.title3,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: OmiSpacing.xs),
                      Text(
                        hasScheduledUpgrade
                            ? l10n.upgradeAlreadyScheduled
                            : (isUnlimited ? l10n.youAreOnAPaidPlan : l10n.planSheetChooseYourPlan),
                        textAlign: TextAlign.center,
                        style: secondary,
                      ),
                      if (isUnlimited && isCancelled) ...[
                        const SizedBox(height: OmiSpacing.xs),
                        // Ended: must create a new subscription. Not yet ended: reactivate without charge.
                        Text(
                          periodEnded ? l10n.planEndedOn(renewalDate) : l10n.planSetToCancelOn(renewalDate),
                          textAlign: TextAlign.center,
                          style: OmiType.subhead.copyWith(color: OmiColors.warning),
                        ),
                      ] else if (isUnlimited && !isCancelled) ...[
                        const SizedBox(height: OmiSpacing.xs),
                        Text(
                          hasScheduledUpgrade ? l10n.annualPlanStartsAutomatically : l10n.planRenewsOn(renewalDate),
                          textAlign: TextAlign.center,
                          style: secondary,
                        ),
                      ],
                      const SizedBox(height: OmiSpacing.xl),
                      // Features list - shown to all users
                      PlanFeatureItem(icon: FontAwesomeIcons.infinity, text: l10n.unlimitedConversations),
                      const SizedBox(height: OmiSpacing.md),
                      PlanFeatureItem(icon: FontAwesomeIcons.solidComments, text: l10n.askOmiAnything),
                      const SizedBox(height: OmiSpacing.md),
                      PlanFeatureItem(icon: FontAwesomeIcons.brain, text: l10n.unlockOmiInfiniteMemory),
                      const SizedBox(height: OmiSpacing.md),
                      PlanFeatureItem(icon: FontAwesomeIcons.globe, text: l10n.availableOnMacMobileWeb),
                      const SizedBox(height: OmiSpacing.xxl),

                      // Training Data Opt-in Option - only show after plans are loaded
                      if (_showTrainingDataOptIn && plansLoaded)
                        Consumer<UserProvider>(
                          builder: (context, userProvider, child) => Padding(
                            padding: const EdgeInsets.only(top: OmiSpacing.xl, bottom: 18),
                            child: TrainingDataOptionCard(
                              optedIn: userProvider.trainingDataOptedIn,
                              status: userProvider.trainingDataStatus,
                              isLoading: userProvider.isLoading,
                              onOptIn: _handleTrainingDataOptIn,
                            ),
                          ),
                        ),

                      if (isUnlimited && !isCancelled)
                        Builder(
                          builder: (context) {
                            if (hasScheduledUpgrade) {
                              return PlanStatusCard(
                                icon: Icons.schedule,
                                title: l10n.upgradeScheduled,
                                message: l10n.annualPlanStartsAutomatically,
                              );
                            }
                            if (_getCurrentPlanDetails()?['interval'] == 'year') {
                              // Already on the annual plan - only the cancel option applies.
                              return PlanStatusCard(
                                icon: Icons.check_circle_outline,
                                iconColor: OmiColors.success,
                                title: l10n.youreOnAnnualPlan,
                                message: l10n.alreadyBestValuePlan,
                              );
                            }
                            return _plansOrPlaceholder(provider);
                          },
                        )
                      else
                        // Cancelled (resubscribe) or on the free plan (upgrade).
                        _plansOrPlaceholder(provider),

                      const SizedBox(height: OmiSpacing.xl),
                      _buildPromoCodeField(),
                      const SizedBox(height: OmiSpacing.md),

                      // Continue/Upgrade — hidden for same-tier annual (nothing to change) and for
                      // desktop-plan → mobile-tier switches.
                      if (shouldShowPlanContinueButton(
                        isOnAnnualPlan: _getCurrentPlanDetails()?['interval'] == 'year',
                        hasScheduledUpgrade: hasScheduledUpgrade,
                        isCancelled: isCancelled,
                        plansLoaded: plansLoaded,
                        selectedTierId: selectedTierId,
                        currentTierId: sub?.plan.wireName,
                        currentGrantsDesktop: sub?.plan.grantsDesktop ?? false,
                      ))
                        // For basic users, show "Upgrade". For paid users upgrading, show "Continue".
                        _primaryAction(
                          key: const ValueKey('plans_sheet_upgrade_button'),
                          label: isUnlimited ? l10n.continueText : l10n.upgrade,
                        ),

                      // Freemium limitations and the downgrade option - basic users only
                      if (!isUnlimited) ...[
                        const SizedBox(height: OmiSpacing.xxl),
                        Text(
                          l10n.freemiumLimitsIntro,
                          textAlign: TextAlign.center,
                          style: secondary.copyWith(fontWeight: FontWeight.w500),
                        ),
                        const SizedBox(height: OmiSpacing.md),
                        PlanFeatureItem(
                          icon: FontAwesomeIcons.carBattery,
                          text: l10n.downgradeLimitBattery,
                          isLimitation: true,
                        ),
                        const SizedBox(height: OmiSpacing.sm),
                        PlanFeatureItem(
                          icon: FontAwesomeIcons.triangleExclamation,
                          text: l10n.downgradeLimitQuality,
                          isLimitation: true,
                        ),
                        const SizedBox(height: OmiSpacing.sm),
                        PlanFeatureItem(
                          icon: FontAwesomeIcons.clock,
                          text: l10n.downgradeLimitDelayNotRealTime,
                          isLimitation: true,
                        ),
                        const SizedBox(height: OmiSpacing.sm),
                        PlanFeatureItem(
                          icon: FontAwesomeIcons.userSlash,
                          text: l10n.downgradeLimitSpeakers,
                          isLimitation: true,
                        ),
                        if (plansLoaded) ...[
                          const SizedBox(height: OmiSpacing.sm),
                          OmiButton.secondary(
                            label: l10n.downgradeToFreemiumAction,
                            expand: true,
                            isLoading: _isSwitchingToFree,
                            onPressed: _handleDowngradeToFreemium,
                          ),
                        ],
                      ],

                      // Resubscribe for cancelled subscriptions
                      if (isCancelled && plansLoaded) _primaryAction(label: l10n.resubscribe),
                      const SizedBox(height: OmiSpacing.md),
                      if (isUnlimited || sub?.stripeSubscriptionId?.isNotEmpty == true) ...[
                        OmiButton.secondary(
                          label: l10n.managePaymentMethod,
                          icon: Icons.credit_card,
                          expand: true,
                          onPressed: _openPaymentPortal,
                        ),
                        const SizedBox(height: OmiSpacing.sm),
                        if (isUnlimited && !isCancelled)
                          OmiButton.tertiary(
                            label: l10n.cancelSubscription,
                            expand: true,
                            onPressed: _handleCancelSubscription,
                          ),
                        const SizedBox(height: OmiSpacing.xs),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildPromoCodeField() {
    OutlineInputBorder border(Color color) =>
        OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide(color: color));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          button: true,
          expanded: _showPromoCodeField,
          child: InkWell(
            onTap: () => setState(() => _showPromoCodeField = !_showPromoCodeField),
            borderRadius: OmiRadius.smAll,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 44),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const ExcludeSemantics(
                    child: Icon(Icons.local_offer_outlined, color: OmiColors.textSecondary, size: 18),
                  ),
                  const SizedBox(width: OmiSpacing.xs),
                  Text(l10n.promoCode, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                  const SizedBox(width: OmiSpacing.xxs),
                  ExcludeSemantics(
                    child: Icon(
                      _showPromoCodeField ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                      color: OmiColors.textSecondary,
                      size: 20,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        if (_showPromoCodeField) ...[
          const SizedBox(height: OmiSpacing.xs),
          TextField(
            controller: _promoCodeController,
            style: OmiType.callout,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              hintText: l10n.enterPromoCode,
              hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
              filled: true,
              fillColor: OmiColors.surface2,
              border: border(OmiColors.border),
              enabledBorder: border(OmiColors.border),
              focusedBorder: border(OmiColors.accent),
              errorBorder: border(OmiColors.danger),
              focusedErrorBorder: border(OmiColors.danger),
              errorText: _promoCodeError,
              contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
              suffixIcon: _promoCodeController.text.isNotEmpty
                  ? OmiIconButton(
                      icon: const Icon(Icons.clear, size: 20),
                      label: l10n.clear,
                      color: OmiColors.textSecondary,
                      onPressed: () {
                        setState(() {
                          _promoCodeController.clear();
                          _promoCodeError = null;
                        });
                      },
                    )
                  : null,
            ),
            onChanged: (_) {
              setState(() => _promoCodeError = null);
            },
          ),
        ],
      ],
    );
  }

  AppLocalizations get l10n => context.l10n;

  /// Groups available plans by plan_id and shows one card per tier.
  Widget _buildTierPlanCards({required Map<String, dynamic> availablePlans}) {
    final plans = (availablePlans['plans'] as List).cast<Map<String, dynamic>>();

    // Group plans by plan_id
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final plan in plans) {
      final planId = plan['plan_id'] as String? ?? '';
      grouped.putIfAbsent(planId, () => []).add(plan);
    }

    // If only 1 tier, fallback to old behavior (monthly/yearly cards)
    if (grouped.length <= 1) {
      return _buildLegacyPlanCards(plans: plans);
    }

    // Tier ordering
    const tierOrder = ['plus', 'unlimited_v2', 'unlimited', 'operator', 'architect'];
    final sortedTierIds = grouped.keys.toList()
      ..sort((a, b) {
        final ai = tierOrder.indexOf(a);
        final bi = tierOrder.indexOf(b);
        return (ai == -1 ? 999 : ai).compareTo(bi == -1 ? 999 : bi);
      });

    // Auto-select current plan's tier, or first tier if none selected
    if (selectedTierId == null) {
      final activeTier = sortedTierIds.firstWhereOrNull((tid) => grouped[tid]!.any((p) => p['is_active'] == true));
      selectedTierId = activeTier ?? sortedTierIds.first;
    }

    final isYearly = selectedPlan == 'yearly';
    final subPlans = context.read<UsageProvider>().subscription?.availablePlans ?? [];

    return Column(
      children: [
        PlanBillingPeriodToggle(
          isYearly: isYearly,
          savePercent: bestAnnualDiscountPercent(grouped.values),
          onChanged: (yearly) => setState(() => selectedPlan = yearly ? 'yearly' : 'monthly'),
        ),
        const SizedBox(height: 18),
        ...sortedTierIds.map((tierId) {
          final tierPlans = grouped[tierId]!;
          final planForPeriod = tierPlans.firstWhereOrNull((p) => p['interval'] == (isYearly ? 'year' : 'month'));
          if (planForPeriod == null) return const SizedBox.shrink();

          // The tier's display name comes from the backend (subscription available_plans).
          final planDataWithName = Map<String, dynamic>.from(planForPeriod)
            ..['title'] = planTitleForTier(tierId, subPlans) ?? planForPeriod['title'] as String;

          return Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
            child: _buildDynamicPlanOption(
              isSelected: selectedTierId == tierId,
              planData: planDataWithName,
              saveTag: isYearly ? _monthsFreeLabel(annualMonthsFree(tierPlans)) : null,
              isPopular: planForPeriod['eyebrow'] == 'Most popular',
              featureSummary: planForPeriod['subtitle'] as String?,
              features: subPlans.firstWhereOrNull((sp) => sp.id == tierId)?.features ?? [],
              desktopAccess: _tierGrantsDesktop(tierId),
              onTap: () {
                HapticFeedback.lightImpact();
                setState(() => selectedTierId = tierId);
              },
            ),
          );
        }),
      ],
    );
  }

  /// Fallback for single-tier plan display (old monthly/yearly cards).
  Widget _buildLegacyPlanCards({required List<Map<String, dynamic>> plans}) {
    return Column(
      children: [
        _buildDynamicPlanOption(
          isSelected: selectedPlan == 'yearly',
          planData: plans.firstWhere((plan) => plan['interval'] == 'year', orElse: () => plans.first),
          saveTag: _monthsFreeLabel(annualMonthsFree(plans)),
          isPopular: true,
          onTap: () {
            HapticFeedback.lightImpact();
            setState(() => selectedPlan = 'yearly');
          },
        ),
        const SizedBox(height: 18),
        _buildDynamicPlanOption(
          isSelected: selectedPlan == 'monthly',
          planData: plans.firstWhere((plan) => plan['interval'] == 'month', orElse: () => plans.first),
          onTap: () {
            HapticFeedback.lightImpact();
            setState(() => selectedPlan = 'monthly');
          },
        ),
      ],
    );
  }

  Widget _buildDynamicPlanOption({
    required bool isSelected,
    required Map<String, dynamic> planData,
    String? saveTag,
    bool isPopular = false,
    String? featureSummary,
    List<String> features = const [],
    bool? desktopAccess,
    required VoidCallback onTap,
  }) {
    final interval = planData['interval'] as String;
    final unitAmount = planData['unit_amount'] as int;
    final isActive = planData['is_active'] as bool? ?? false;

    // An "Ends on [date]" badge only on the cancelled subscription's own price.
    final sub = context.read<UsageProvider>().subscription?.subscription;
    final isCancelled = sub?.cancelAtPeriodEnd ?? false;
    String? endsOnDate;
    if (isCancelled && sub?.currentPeriodEnd != null && sub?.currentPriceId == planData['id']) {
      endsOnDate = OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(sub!.currentPeriodEnd! * 1000));
    }

    return PlanOptionCard(
      isSelected: isSelected,
      saveTag: saveTag,
      isPopular: isPopular,
      title: planData['title'] as String,
      subtitle: interval == 'year' ? l10n.annualBillingSummary(12, '\$${unitAmount / 100}') : null,
      price: planData['price_string'] as String,
      onTap: isActive ? () {} : onTap,
      isActive: isActive && !isCancelled,
      endsOnDate: endsOnDate,
      featureSummary: featureSummary,
      features: features,
      desktopAccess: desktopAccess,
    );
  }

  /// Whether a plan tier includes the desktop (macOS) app. Neo (unlimited) is
  /// mobile/web only; Operator and Architect include desktop. Keep in sync with
  /// backend `DESKTOP_ENTITLED_PLAN_TYPES`. Returns null for unknown tiers.
  bool? _tierGrantsDesktop(String tierId) {
    switch (tierId) {
      case 'operator':
      case 'architect':
        return true;
      case 'unlimited':
      case 'plus':
      case 'unlimited_v2':
        return false;
      default:
        return null;
    }
  }

  String? _monthsFreeLabel(int? months) => months == null ? null : l10n.monthsFreeBadge(months);
}
