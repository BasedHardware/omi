import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/paypal_setup_page.dart';
import 'package:omi/pages/payments/stripe_connect_setup.dart';
import 'package:omi/pages/payments/widgets/payment_method_card.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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
    MixpanelManager().paymentsPageOpened();
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
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Color(0xFF35343B),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.info_outline,
            color: Colors.white70,
            size: 24,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              context.l10n.connectPaymentMethodInfo,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PaymentMethodProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          title: Text(context.l10n.payments, style: const TextStyle(color: Colors.white)),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: Colors.white),
            onPressed: () => Navigator.pop(context),
          ),
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
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Consumer<PaymentMethodProvider>(
                    builder: (context, provider, child) {
                      final activeMethod = provider.activeMethod;
                      final hasActiveMethod = activeMethod != null;

                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (!hasActiveMethod) ...[_buildInfoCard(), const SizedBox(height: 28)],
                          if (hasActiveMethod) ...[
                            _buildActiveMethodCard(activeMethod, provider),
                            const SizedBox(height: 24)
                          ],
                          Text(
                            context.l10n.availablePaymentMethods,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                          const SizedBox(height: 16),
                          ..._buildOtherMethodCards(provider, activeMethod),
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
    });
  }

  Widget _buildActiveMethodCard(PaymentMethodType method, PaymentMethodProvider provider) {
    final config = method == PaymentMethodType.stripe
        ? PaymentMethodConfig.stripe(
            title: context.l10n.paymentMethodStripe,
            subtitle: _getPaymentSubtitle(isActive: true, isConnected: true),
            onManageTap: () {
              MixpanelManager().paymentMethodSelected(methodName: 'Stripe');
              routeToPage(context, const StripeConnectSetup());
            },
            isActive: true,
            isConnected: true,
          )
        : PaymentMethodConfig.paypal(
            title: context.l10n.paymentMethodPayPal,
            subtitle: _getPaymentSubtitle(isActive: true, isConnected: true),
            onManageTap: () {
              MixpanelManager().paymentMethodSelected(methodName: 'PayPal');
              routeToPage(context, const PaypalSetupPage());
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
              MixpanelManager().track('Manage Stripe');
              routeToPage(context, const StripeConnectSetup());
            },
            onSetActiveTap: () {
              provider.setActiveMethod(PaymentMethodType.stripe);
              MixpanelManager().track('Set Stripe as active');
            },
            isConnected: true,
            isActive: false,
          ),
          true
        ),
      if (provider.isPayPalConnected && activeMethod != PaymentMethodType.paypal)
        (
          PaymentMethodConfig.paypal(
            title: context.l10n.paymentMethodPayPal,
            subtitle: _getPaymentSubtitle(isActive: false, isConnected: true),
            onManageTap: () {
              MixpanelManager().track('Manage PayPal');
              routeToPage(context, const PaypalSetupPage());
            },
            onSetActiveTap: () {
              provider.setActiveMethod(PaymentMethodType.paypal);
              MixpanelManager().track('Set PayPal as active');
            },
            isConnected: true,
            isActive: false,
          ),
          false
        ),
      if (!provider.isStripeConnected)
        (
          PaymentMethodConfig.stripe(
            title: context.l10n.paymentMethodStripe,
            subtitle: _getPaymentSubtitle(isActive: false, isConnected: false),
            onManageTap: () {
              MixpanelManager().track('Manage Stripe');
              routeToPage(context, const StripeConnectSetup());
            },
            isConnected: false,
          ),
          true
        ),
      if (!provider.isPayPalConnected)
        (
          PaymentMethodConfig.paypal(
            title: context.l10n.paymentMethodPayPal,
            subtitle: _getPaymentSubtitle(isActive: false, isConnected: false),
            onManageTap: () {
              MixpanelManager().track('Manage PayPal');
              routeToPage(context, const PaypalSetupPage());
            },
            isConnected: false,
          ),
          false
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
