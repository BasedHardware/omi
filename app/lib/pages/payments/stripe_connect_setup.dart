import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:flutter_svg/svg.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/payments/widgets/country_bottom_sheet.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/animated_loading_button.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'payment_method_provider.dart';

class StripeConnectSetup extends StatefulWidget {
  const StripeConnectSetup({super.key});

  @override
  State<StripeConnectSetup> createState() => _StripeConnectSetupState();
}

class _StripeConnectSetupState extends State<StripeConnectSetup> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    context.read<PaymentMethodProvider>().getSupportedCountries();
  }

  @override
  void dispose() {
    if (context.mounted) {
      context.read<PaymentMethodProvider>().stopStripePolling();
    }
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PaymentMethodProvider>(builder: (context, provider, child) {
      return PopScope(
        onPopInvoked: (_) async {
          provider.stopStripePolling();
        },
        child: Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.transparent,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
              onPressed: () {
                provider.stopStripePolling();
                Navigator.pop(context);
              },
            ),
          ),
          body: SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                return SingleChildScrollView(
                  padding: const EdgeInsets.all(24.0),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: constraints.maxHeight),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(height: 20),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const SizedBox(
                              width: 18,
                            ),
                            Container(
                              padding: const EdgeInsets.all(10),
                              decoration: const BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                              ),
                              child: Image.asset(
                                Assets.images.herologo.path,
                                width: 26,
                                color: Colors.black,
                              ),
                            ),
                            Transform.translate(
                              offset: const Offset(-18, 0),
                              child: Container(
                                padding: const EdgeInsets.all(14),
                                decoration: const BoxDecoration(
                                  color: Color(0xFF635BFF),
                                  shape: BoxShape.circle,
                                ),
                                child: SvgPicture.asset(
                                  Assets.images.stripeLogo,
                                  width: 40,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 32),
                        if (!provider.isStripePolling && !provider.isStripeConnected) ...[
                          Text(
                            context.l10n.getPaidThroughStripe,
                            style: const TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 48),
                          _buildFeatureRow(
                            icon: Icons.payments_rounded,
                            title: context.l10n.monthlyPayouts,
                            description: context.l10n.monthlyPayoutsDescription,
                          ),
                          const SizedBox(height: 24),
                          _buildFeatureRow(
                            icon: Icons.shield_outlined,
                            title: context.l10n.secureAndReliable,
                            description: context.l10n.stripeSecureDescription,
                          ),
                          const SizedBox(height: 24),
                          provider.stripeConnectionState == PaymentConnectionState.notConnected
                              ? Column(
                                  children: [
                                    const SizedBox(height: 8),
                                    ElevatedButton(
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.white.withOpacity(0.1),
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                      ),
                                      onPressed: () {
                                        provider.updateSearchQuery('');
                                        showModalBottomSheet(
                                          context: context,
                                          isScrollControlled: true,
                                          backgroundColor: const Color(0xFF1A1A1A),
                                          shape: const RoundedRectangleBorder(
                                            borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                          ),
                                          builder: (context) {
                                            return const CountryBottomSheet();
                                          },
                                        );
                                      },
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Row(
                                            children: [
                                              if (!(provider.selectedCountryId?.isEmpty ?? true) &&
                                                  provider.selectedCountryId != null)
                                                Text(
                                                  countryFlagFromCode(provider.selectedCountryId!),
                                                  style: const TextStyle(fontSize: 24),
                                                ),
                                              const SizedBox(width: 8),
                                              Text(
                                                provider.selectedCountryId?.isEmpty ?? true
                                                    ? context.l10n.selectYourCountry
                                                    : ((provider.filteredCountries.firstWhereOrNull((country) =>
                                                                country['id'] ==
                                                                provider.selectedCountryId)?['name'] as String?)
                                                            ?.decodeString ??
                                                        context.l10n.selectYourCountry),
                                                style: const TextStyle(color: Colors.white),
                                              ),
                                            ],
                                          ),
                                          const Icon(Icons.arrow_drop_down, color: Colors.white),
                                        ],
                                      ),
                                    ),
                                  ],
                                )
                              : const SizedBox(),
                          const SizedBox(height: 12),
                          provider.stripeConnectionState == PaymentConnectionState.notConnected
                              ? Container(
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: Colors.red.withOpacity(0.1),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Row(
                                    children: [
                                      Icon(Icons.warning_amber_rounded, color: Colors.red[400], size: 20),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: Text(
                                          context.l10n.countrySelectionPermanent,
                                          style: TextStyle(
                                            color: Colors.red[400],
                                            fontSize: 14,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                )
                              : const SizedBox(),
                          const SizedBox(height: 24),
                          Text(
                            context.l10n.byClickingConnectNow,
                            style: TextStyle(
                              color: Colors.grey[400],
                              fontSize: 14,
                            ),
                          ),
                          const SizedBox(height: 4),
                          GestureDetector(
                            onTap: () {
                              launchUrl(Uri.parse('https://stripe.com/connect-account/legal'));
                            },
                            child: Text(
                              context.l10n.stripeConnectedAccountAgreement,
                              style: const TextStyle(
                                color: Color(0xFF635BFF),
                                fontSize: 14,
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          AnimatedLoadingButton(
                            text: context.l10n.connectNow,
                            loaderColor: Colors.black,
                            onPressed: provider.stripeConnectionState == PaymentConnectionState.inComplete ||
                                    provider.selectedCountryId != null
                                ? () async {
                                    MixpanelManager().track('Stripe Connect Started');
                                    var url = await provider.connectStripe();
                                    if (url != null) {
                                      provider.startStripePolling();
                                      await launchUrl(Uri.parse(url));
                                    } else {
                                      AppSnackbar.showSnackbarError(context.l10n.errorConnectingToStripe);
                                    }
                                  }
                                : () async {},
                            color: provider.stripeConnectionState == PaymentConnectionState.inComplete ||
                                    provider.selectedCountryId != null
                                ? Colors.white
                                : Colors.grey,
                            textStyle: TextStyle(
                              fontSize: 16,
                              color: provider.stripeConnectionState == PaymentConnectionState.inComplete ||
                                      provider.selectedCountryId != null
                                  ? Colors.black
                                  : Colors.grey[600],
                            ),
                            width: MediaQuery.of(context).size.width * 0.8,
                          ),
                        ],
                        if (provider.isStripePolling && !provider.isStripeConnected) ...[
                          const SizedBox(height: 48),
                          AnimatedBuilder(
                            animation: _pulseController,
                            builder: (context, child) {
                              return Container(
                                width: 80,
                                height: 80,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: const Color(0xFF635BFF),
                                    width: 3,
                                  ),
                                  boxShadow: [
                                    BoxShadow(
                                      color: const Color(0xFF635BFF).withOpacity(0.5),
                                      blurRadius: 20 * _pulseController.value,
                                      spreadRadius: 10 * _pulseController.value,
                                    ),
                                  ],
                                ),
                                child: const Center(
                                  child: Icon(
                                    Icons.sync,
                                    color: Color(0xFF635BFF),
                                    size: 40,
                                  ),
                                ),
                              );
                            },
                          ),
                          const SizedBox(height: 48),
                          Text(
                            context.l10n.connectingYourStripeAccount,
                            style: const TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            context.l10n.stripeOnboardingInstructions,
                            style: TextStyle(
                              fontSize: 16,
                              color: Colors.grey[400],
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 24),
                          AnimatedLoadingButton(
                            text: context.l10n.failedTryAgain,
                            onPressed: () async {
                              MixpanelManager().track('Stripe Connect Retry');
                              var res = await provider.connectStripe();
                              if (res != null) {
                                provider.startStripePolling();
                                await launchUrl(Uri.parse(res));
                              } else {
                                AppSnackbar.showSnackbarError(context.l10n.errorConnectingToStripe);
                              }
                            },
                            color: Colors.white,
                            loaderColor: Colors.black,
                            textStyle: const TextStyle(
                              fontSize: 16,
                              color: Colors.black,
                            ),
                            width: MediaQuery.of(context).size.width * 0.8,
                          ),
                          TextButton(
                              onPressed: () {
                                MixpanelManager().track('Stripe Connect Later');
                                provider.stopStripePolling();
                                Navigator.pop(context);
                              },
                              child: Text(
                                context.l10n.illDoItLater,
                                style: TextStyle(color: Colors.grey[400]),
                              )),
                        ],
                        if (!provider.isStripePolling && provider.isStripeConnected) ...[
                          const SizedBox(height: 48),
                          Container(
                            padding: const EdgeInsets.all(24),
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  const Color(0xFF635BFF).withOpacity(0.15),
                                  Colors.purple.shade900.withOpacity(0.1),
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: const Color(0xFF635BFF).withOpacity(0.3),
                                width: 1,
                              ),
                            ),
                            child: Column(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF635BFF).withOpacity(0.1),
                                    shape: BoxShape.circle,
                                  ),
                                  child: const Icon(
                                    Icons.check_circle_outline_rounded,
                                    color: Color(0xFF635BFF),
                                    size: 48,
                                  ),
                                ),
                                const SizedBox(height: 24),
                                Text(
                                  '${context.l10n.successfullyConnected} 🎉',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  context.l10n.stripeReadyForPayments,
                                  style: TextStyle(
                                    fontSize: 16,
                                    color: Colors.grey[400],
                                    height: 1.5,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 24),
                          AnimatedLoadingButton(
                            text: context.l10n.updateStripeDetails,
                            onPressed: () async {
                              MixpanelManager().track('Stripe Connect Update');
                              var url = await provider.connectStripe();
                              if (url != null) {
                                provider.startStripePolling();
                                await launchUrl(Uri.parse(url));
                              } else {
                                AppSnackbar.showSnackbarError(context.l10n.errorUpdatingStripeDetails);
                              }
                            },
                            color: Colors.white,
                            loaderColor: Colors.black,
                            textStyle: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w500,
                              color: Colors.black,
                            ),
                            width: MediaQuery.of(context).size.width * 0.8,
                          ),
                          TextButton(
                            onPressed: () {
                              provider.stopStripePolling();
                              Navigator.pop(context);
                            },
                            child: Text(
                              context.l10n.goBack,
                              style: TextStyle(color: Colors.grey[400]),
                            ),
                          ),
                        ],
                        const SizedBox(height: 36),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      );
    });
  }

  Widget _buildFeatureRow({
    required IconData icon,
    required String title,
    required String description,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: const Color(0xFF635BFF).withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            icon,
            color: const Color(0xFF635BFF),
            size: 24,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                description,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[400],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
