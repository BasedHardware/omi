import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/stripe_connect_setup.dart';
import 'package:omi/pages/payments/widgets/payment_method_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'models/payment_method_config.dart';

class PaymentsPage extends StatefulWidget {
  const PaymentsPage({super.key});

  @override
  State<PaymentsPage> createState() => _PaymentsPageState();
}

class _PaymentsPageState extends State<PaymentsPage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.paymentsPageOpened();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<PaymentMethodProvider>().getPaymentMethodsStatus();
    });
  }

  String _getPaymentSubtitle({required bool isActive, required bool isConnected}) {
    if (isActive) return context.l10n.paymentStatusActive;
    if (isConnected) return context.l10n.paymentStatusConnected;
    return context.l10n.paymentStatusNotConnected;
  }

  Widget _buildInfoCard() {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border, width: 1),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, color: OmiColors.textSecondary, size: 24),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Text(
              context.l10n.connectPaymentMethodInfo,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PaymentMethodProvider>(
      builder: (context, provider, child) {
        return Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: AppBar(
            leading: const OmiBackButton(),
            title: Text(context.l10n.payments),
          ),
          body: Skeletonizer(
            enabled: provider.isLoading,
            child: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.l10n.selectedPaymentMethod,
                      style: OmiType.title3,
                    ),
                    const SizedBox(height: 18),
                    Consumer<PaymentMethodProvider>(
                      builder: (context, provider, child) {
                        // PayPal is no longer offered; only treat Stripe as a valid active method.
                        final activeMethod =
                            provider.activeMethod == PaymentMethodType.stripe ? provider.activeMethod : null;
                        final hasActiveMethod = activeMethod != null;

                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (!hasActiveMethod) ...[_buildInfoCard(), const SizedBox(height: 28)],
                            if (hasActiveMethod) ...[_buildActiveMethodCard(provider), const SizedBox(height: 24)],
                            Text(
                              context.l10n.availablePaymentMethods,
                              style: OmiType.title3,
                            ),
                            const SizedBox(height: 16),
                            ..._buildOtherMethodCards(provider, activeMethod),
                            const SizedBox(height: 12),
                            _buildComingSoonCard(),
                          ],
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildComingSoonCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border, width: 1),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
            child: const Icon(Icons.schedule_outlined, color: OmiColors.textTertiary, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              context.l10n.morePaymentMethodsComingSoon,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveMethodCard(PaymentMethodProvider provider) {
    final config = PaymentMethodConfig.stripe(
      title: context.l10n.paymentMethodStripe,
      subtitle: _getPaymentSubtitle(isActive: true, isConnected: true),
      onManageTap: () {
        PlatformManager.instance.analytics.paymentMethodSelected(methodName: 'Stripe');
        routeToPage(context, const StripeConnectSetup());
      },
      isActive: true,
      isConnected: true,
    );

    return PaymentMethodCard(
      icon: config.icon,
      title: config.title,
      subtitle: config.subtitle,
      backgroundColor: config.backgroundColor,
      onManageTap: config.onManageTap,
      onSetActiveTap: config.onSetActiveTap,
      isActive: config.isActive,
      isConnected: config.isConnected,
    );
  }

  List<Widget> _buildOtherMethodCards(PaymentMethodProvider provider, PaymentMethodType? activeMethod) {
    final paymentMethods = [
      if (provider.isStripeConnected && activeMethod != PaymentMethodType.stripe)
        (
          PaymentMethodConfig.stripe(
            title: context.l10n.paymentMethodStripe,
            subtitle: _getPaymentSubtitle(isActive: false, isConnected: true),
            onManageTap: () {
              PlatformManager.instance.analytics.track('Manage Stripe');
              routeToPage(context, const StripeConnectSetup());
            },
            onSetActiveTap: () {
              provider.setActiveMethod(PaymentMethodType.stripe);
              PlatformManager.instance.analytics.track('Set Stripe as active');
            },
            isConnected: true,
            isActive: false,
          ),
          true,
        ),
      if (!provider.isStripeConnected)
        (
          PaymentMethodConfig.stripe(
            title: context.l10n.paymentMethodStripe,
            subtitle: _getPaymentSubtitle(isActive: false, isConnected: false),
            onManageTap: () {
              PlatformManager.instance.analytics.track('Manage Stripe');
              routeToPage(context, const StripeConnectSetup());
            },
            isConnected: false,
          ),
          true,
        ),
    ];

    return List.generate(
      paymentMethods.length,
      (index) => Column(
        children: [
          PaymentMethodCard.fromConfig(paymentMethods[index].$1),
          if (paymentMethods[index].$2 && index < paymentMethods.length - 1) const SizedBox(height: 12),
        ],
      ),
    );
  }
}
