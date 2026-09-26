import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:flutter_svg/svg.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/payments/widgets/country_bottom_sheet.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
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
  late final PaymentMethodProvider _payments = context.read<PaymentMethodProvider>();

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
    _payments.getSupportedCountries();
  }

  @override
  void dispose() {
    // The provider was captured while mounted; context lookups no longer work in dispose.
    _payments.stopStripePolling();
    _pulseController.dispose();
    super.dispose();
  }

  bool _canConnect(PaymentMethodProvider provider) =>
      provider.stripeConnectionState == PaymentConnectionState.inComplete || provider.selectedCountryId != null;

  /// Starts (or restarts) Stripe onboarding in the browser and polls for completion.
  Future<void> _connect(PaymentMethodProvider provider, {required String event, required String errorMessage}) async {
    PlatformManager.instance.analytics.track(event);
    final url = await provider.connectStripe();
    if (url != null) {
      provider.startStripePolling();
      await launchUrl(Uri.parse(url));
    } else if (mounted) {
      OmiFeedback.error(context, errorMessage);
    }
  }

  void _showCountryPicker(PaymentMethodProvider provider) {
    provider.updateSearchQuery('');
    showOmiSheet<void>(
      context: context,
      title: context.l10n.selectYourCountry,
      builder: (context) => const CountryBottomSheet(),
    );
  }

  String _selectedCountryName(PaymentMethodProvider provider) {
    if (provider.selectedCountryId?.isEmpty ?? true) return context.l10n.selectYourCountry;
    // Not filteredCountries: that still carries the picker's last search.
    final name = provider.supportedCountries.firstWhereOrNull(
      (country) => country['id'] == provider.selectedCountryId,
    )?['name'] as String?;
    return name?.decodeString ?? context.l10n.selectYourCountry;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PaymentMethodProvider>(
      builder: (context, provider, child) {
        // Every way out (back button, edge swipe, system back, the in-page buttons) pops the route,
        // and every pop stops polling.
        return PopScope(
          onPopInvokedWithResult: (_, __) async {
            provider.stopStripePolling();
          },
          child: Scaffold(
            backgroundColor: OmiColors.surface0,
            appBar: AppBar(leading: const OmiBackButton()),
            body: SafeArea(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  return SingleChildScrollView(
                    padding: const EdgeInsets.all(OmiSpacing.xl),
                    child: ConstrainedBox(
                      constraints: BoxConstraints(minHeight: constraints.maxHeight),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const SizedBox(height: OmiSpacing.lg),
                          _buildLogos(),
                          const SizedBox(height: OmiSpacing.xxl),
                          if (!provider.isStripePolling && !provider.isStripeConnected)
                            ..._buildConnectSection(provider),
                          if (provider.isStripePolling && !provider.isStripeConnected)
                            ..._buildPollingSection(provider),
                          if (!provider.isStripePolling && provider.isStripeConnected)
                            ..._buildConnectedSection(provider),
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
      },
    );
  }

  Widget _buildLogos() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const SizedBox(width: 18),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
          child: Image.asset(Assets.images.herologo.path, width: 26, color: OmiColors.onAccent),
        ),
        Transform.translate(
          offset: const Offset(-18, 0),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: const BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
            child: SvgPicture.asset(
              Assets.images.stripeLogo,
              width: 40,
              colorFilter: const ColorFilter.mode(OmiColors.textPrimary, BlendMode.srcIn),
            ),
          ),
        ),
      ],
    );
  }

  List<Widget> _buildConnectSection(PaymentMethodProvider provider) {
    final notConnected = provider.stripeConnectionState == PaymentConnectionState.notConnected;
    final hasCountry = !(provider.selectedCountryId?.isEmpty ?? true) && provider.selectedCountryId != null;
    return [
      Text(
        context.l10n.getPaidThroughStripe,
        style: OmiType.title2.copyWith(fontWeight: FontWeight.w700),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 48),
      _buildFeatureRow(
        icon: Icons.payments_rounded,
        title: context.l10n.monthlyPayouts,
        description: context.l10n.monthlyPayoutsDescription,
      ),
      const SizedBox(height: OmiSpacing.xl),
      _buildFeatureRow(
        icon: Icons.shield_outlined,
        title: context.l10n.secureAndReliable,
        description: context.l10n.stripeSecureDescription,
      ),
      const SizedBox(height: OmiSpacing.xl),
      if (notConnected) ...[
        const SizedBox(height: OmiSpacing.xs),
        Material(
          color: OmiColors.surface2,
          borderRadius: OmiRadius.mdAll,
          child: InkWell(
            borderRadius: OmiRadius.mdAll,
            onTap: () => _showCountryPicker(provider),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 48),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
                child: Row(
                  children: [
                    if (hasCountry) ...[
                      Text(countryFlagFromCode(provider.selectedCountryId!), style: OmiType.title2),
                      const SizedBox(width: OmiSpacing.xs),
                    ],
                    Expanded(child: Text(_selectedCountryName(provider), style: OmiType.callout)),
                    const Icon(Icons.arrow_drop_down, color: OmiColors.textPrimary),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
      const SizedBox(height: OmiSpacing.sm),
      if (notConnected)
        Container(
          padding: const EdgeInsets.all(OmiSpacing.sm),
          decoration: const BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.smAll),
          child: Row(
            children: [
              const Icon(Icons.warning_amber_rounded, color: OmiColors.danger, size: 20),
              const SizedBox(width: OmiSpacing.xs),
              Expanded(
                child: Text(
                  context.l10n.countrySelectionPermanent,
                  style: OmiType.footnote.copyWith(color: OmiColors.danger),
                ),
              ),
            ],
          ),
        ),
      const SizedBox(height: OmiSpacing.xl),
      Text(context.l10n.byClickingConnectNow, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
      const SizedBox(height: OmiSpacing.xxs),
      GestureDetector(
        onTap: () {
          launchUrl(Uri.parse('https://stripe.com/connect-account/legal'));
        },
        child: Text(
          context.l10n.stripeConnectedAccountAgreement,
          style: OmiType.footnote.copyWith(decoration: TextDecoration.underline),
        ),
      ),
      const SizedBox(height: 18),
      OmiButton(
        label: context.l10n.connectNow,
        expand: true,
        onPressed: _canConnect(provider)
            ? () => _connect(
                  provider,
                  event: 'Stripe Connect Started',
                  errorMessage: context.l10n.errorConnectingToStripe,
                )
            : null,
      ),
    ];
  }

  List<Widget> _buildPollingSection(PaymentMethodProvider provider) {
    return [
      const SizedBox(height: 48),
      AnimatedBuilder(
        animation: _pulseController,
        builder: (context, child) {
          return Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: OmiColors.accent, width: 3),
              boxShadow: [
                BoxShadow(
                  color: OmiColors.accent.withValues(alpha: 0.25),
                  blurRadius: 20 * _pulseController.value,
                  spreadRadius: 10 * _pulseController.value,
                ),
              ],
            ),
            child: const Center(child: Icon(Icons.sync, color: OmiColors.accent, size: 40)),
          );
        },
      ),
      const SizedBox(height: 48),
      Text(
        context.l10n.connectingYourStripeAccount,
        style: OmiType.title2.copyWith(fontWeight: FontWeight.w700),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: OmiSpacing.md),
      Text(
        context.l10n.stripeOnboardingInstructions,
        style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: OmiSpacing.xl),
      OmiButton(
        label: context.l10n.failedTryAgain,
        expand: true,
        onPressed: () => _connect(
          provider,
          event: 'Stripe Connect Retry',
          errorMessage: context.l10n.errorConnectingToStripe,
        ),
      ),
      const SizedBox(height: OmiSpacing.xs),
      OmiButton.tertiary(
        label: context.l10n.illDoItLater,
        expand: true,
        onPressed: () {
          PlatformManager.instance.analytics.track('Stripe Connect Later');
          provider.stopStripePolling();
          Navigator.pop(context);
        },
      ),
    ];
  }

  List<Widget> _buildConnectedSection(PaymentMethodProvider provider) {
    return [
      const SizedBox(height: 48),
      Container(
        padding: const EdgeInsets.all(OmiSpacing.xl),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 1),
        ),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(OmiSpacing.md),
              decoration: const BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
              child: const Icon(Icons.check_circle_outline_rounded, color: OmiColors.success, size: 48),
            ),
            const SizedBox(height: OmiSpacing.xl),
            Text(
              context.l10n.successfullyConnected,
              style: OmiType.title2.copyWith(fontWeight: FontWeight.w700),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: OmiSpacing.md),
            Text(
              context.l10n.stripeReadyForPayments,
              style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.5),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
      const SizedBox(height: OmiSpacing.xl),
      OmiButton(
        label: context.l10n.updateStripeDetails,
        expand: true,
        onPressed: () => _connect(
          provider,
          event: 'Stripe Connect Update',
          errorMessage: context.l10n.errorUpdatingStripeDetails,
        ),
      ),
      const SizedBox(height: OmiSpacing.xs),
      OmiButton.tertiary(
        label: context.l10n.goBack,
        expand: true,
        onPressed: () {
          provider.stopStripePolling();
          Navigator.pop(context);
        },
      ),
    ];
  }

  Widget _buildFeatureRow({required IconData icon, required String title, required String description}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(OmiSpacing.xs),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          child: Icon(icon, color: OmiColors.textPrimary, size: 24),
        ),
        const SizedBox(width: OmiSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
              const SizedBox(height: OmiSpacing.xxs),
              Text(description, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
      ],
    );
  }
}
