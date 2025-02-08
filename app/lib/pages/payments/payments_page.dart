import 'package:flutter/material.dart';
import 'package:friend_private/pages/payments/payment_method_provider.dart';
import 'package:friend_private/pages/payments/stripe_connect_setup.dart';
import 'package:friend_private/pages/payments/widgets/payment_method_card.dart';
import 'package:friend_private/pages/payments/paypal_setup_page.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<PaymentMethodProvider>().getPaymentMethodsStatus();
    });
  }

  Widget _buildInfoCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.grey.shade800,
          width: 1,
        ),
      ),
      child: const Row(
        children: [
          Icon(
            Icons.info_outline,
            color: Colors.white70,
            size: 24,
          ),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Connect a payment method below to start receiving payouts for your apps.',
              style: TextStyle(
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
          title: const Text('Payments', style: TextStyle(color: Colors.white)),
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
                  const Text(
                    'Selected Payment Method',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
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
                          const Text(
                            'Available Payment Methods',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w600,
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
            onManageTap: () {
              routeToPage(context, const StripeConnectSetup());
            },
            isActive: true,
            isConnected: true,
          )
        : PaymentMethodConfig.paypal(
            onManageTap: () {
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
            onManageTap: () {
              routeToPage(context, const StripeConnectSetup());
            },
            onSetActiveTap: () {
              provider.setActiveMethod(PaymentMethodType.stripe);
            },
            isConnected: true,
            isActive: false,
          ),
          true
        ),
      if (provider.isPayPalConnected && activeMethod != PaymentMethodType.paypal)
        (
          PaymentMethodConfig.paypal(
            onManageTap: () {
              routeToPage(context, const PaypalSetupPage());
            },
            onSetActiveTap: () {
              provider.setActiveMethod(PaymentMethodType.paypal);
            },
            isConnected: true,
            isActive: false,
          ),
          false
        ),
      if (!provider.isStripeConnected)
        (
          PaymentMethodConfig.stripe(
            onManageTap: () {
              routeToPage(context, const StripeConnectSetup());
            },
            isConnected: false,
          ),
          true
        ),
      if (!provider.isPayPalConnected)
        (
          PaymentMethodConfig.paypal(
            onManageTap: () {
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
