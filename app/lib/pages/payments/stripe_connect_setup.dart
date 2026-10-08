import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:flutter_svg/svg.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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

const _stripeAgreementUrl = 'https://stripe.com/connect-account/legal';

/// The native country choice's "no country yet" option; it never sets a country.
const _unsetCountry = '__unset__';

final _countryId = RegExp(r'^[A-Z]{2}$');

class _StripeConnectSetupState extends State<StripeConnectSetup> {
  late final PaymentMethodProvider _payments = context.read<PaymentMethodProvider>();

  @override
  void initState() {
    super.initState();
    _payments.getSupportedCountries();
  }

  @override
  void dispose() {
    // The provider was captured while mounted; context lookups no longer work in dispose.
    _payments.stopStripePolling();
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
          child: _nativeStripeSurface(
            provider,
            Scaffold(
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
          ),
        );
      },
    );
  }

  /// The setup steps as native rows. Connecting, polling and the browser hand-off stay with
  /// [_connect], the provider and url_launcher; the account link never enters a snapshot.
  /// Countries the native choice cannot carry exactly keep the complete Flutter screen.
  Widget _nativeStripeSurface(PaymentMethodProvider provider, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final polling = provider.isStripePolling && !provider.isStripeConnected;
    final connected = !provider.isStripePolling && provider.isStripeConnected;
    final connect = !provider.isStripePolling && !provider.isStripeConnected;
    final notConnected = provider.stripeConnectionState == PaymentConnectionState.notConnected;
    final countries = connect && notConnected ? _nativeCountryOptions(provider) : const <String, String>{};
    if (countries == null) return classic;
    final selected = provider.selectedCountryId;
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.paymentMethodStripe,
        fallback: classic,
        // Only polling: the country fetch flips isLoading without notifying, so it could stick.
        loading: polling,
        toolbar: [
          NativeRow('stripe_back', l10n.back,
              symbol: 'chevron.left', action: (_) async => await Navigator.of(context).maybePop()),
        ],
        sections: [
          if (connect) ...[
            NativeSection('stripe_benefits', [
              NativeRow('stripe_headline', l10n.getPaidThroughStripe, kind: 'label'),
              NativeRow('stripe_monthly', l10n.monthlyPayouts,
                  kind: 'label', subtitle: l10n.monthlyPayoutsDescription, symbol: 'banknote'),
              NativeRow('stripe_secure', l10n.secureAndReliable,
                  kind: 'label', subtitle: l10n.stripeSecureDescription, symbol: 'lock.shield'),
            ]),
            NativeSection('stripe_setup', [
              if (notConnected) ...[
                NativeRow('stripe_country', l10n.selectYourCountry,
                    kind: 'choice',
                    value: selected != null && countries.containsKey(selected) ? selected : _unsetCountry,
                    options: countries,
                    optionSearch: l10n.searchCountries,
                    optionClose: l10n.close, action: (value) {
                  if (value != _unsetCountry) provider.setSelectedCountryId(value as String);
                }),
                NativeRow('stripe_country_permanent', l10n.countrySelectionPermanent,
                    kind: 'label', symbol: 'exclamationmark.triangle', destructive: true),
              ],
              NativeRow('stripe_terms', l10n.byClickingConnectNow, kind: 'label'),
              NativeRow('stripe_agreement', l10n.stripeConnectedAccountAgreement,
                  kind: 'navigation', symbol: 'doc.text', action: (_) => launchUrl(Uri.parse(_stripeAgreementUrl))),
              NativeRow('stripe_connect', l10n.connectNow,
                  symbol: 'link',
                  enabled: _canConnect(provider),
                  action: (_) => _connect(
                        provider,
                        event: 'Stripe Connect Started',
                        errorMessage: l10n.errorConnectingToStripe,
                      )),
            ]),
          ],
          if (polling)
            NativeSection('stripe_polling', [
              NativeRow('stripe_connecting', l10n.connectingYourStripeAccount,
                  kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
              NativeRow('stripe_instructions', l10n.stripeOnboardingInstructions, kind: 'label'),
              NativeRow('stripe_retry', l10n.failedTryAgain,
                  symbol: 'arrow.clockwise',
                  action: (_) => _connect(
                        provider,
                        event: 'Stripe Connect Retry',
                        errorMessage: l10n.errorConnectingToStripe,
                      )),
              NativeRow('stripe_later', l10n.illDoItLater, action: (_) {
                PlatformManager.instance.analytics.track('Stripe Connect Later');
                provider.stopStripePolling();
                Navigator.pop(context);
              }),
            ]),
          if (connected)
            NativeSection('stripe_connected', [
              NativeRow('stripe_connected_status', l10n.successfullyConnected,
                  kind: 'label', subtitle: l10n.stripeReadyForPayments, symbol: 'checkmark.circle'),
              NativeRow('stripe_update', l10n.updateStripeDetails,
                  symbol: 'arrow.triangle.2.circlepath',
                  action: (_) => _connect(
                        provider,
                        event: 'Stripe Connect Update',
                        errorMessage: l10n.errorUpdatingStripeDetails,
                      )),
              NativeRow('stripe_go_back', l10n.goBack, action: (_) {
                provider.stopStripePolling();
                Navigator.pop(context);
              }),
            ]),
        ],
      ),
    );
  }

  /// '__unset__' plus every supported country as '<flag> <name>', or null when a country cannot
  /// be carried exactly (an invalid or repeated id, a missing name): no country is ever dropped.
  Map<String, String>? _nativeCountryOptions(PaymentMethodProvider provider) {
    final options = <String, String>{_unsetCountry: context.l10n.selectYourCountry};
    for (final country in provider.supportedCountries) {
      final id = country['id'];
      final name = country['name'];
      if (id is! String || !_countryId.hasMatch(id) || name is! String || options.containsKey(id)) return null;
      options[id] = '${countryFlagFromCode(id)} ${name.decodeString}';
    }
    // A selection the list does not carry keeps its flag beside the generic label, as the classic row does.
    final selected = provider.selectedCountryId;
    if (selected != null && selected.isNotEmpty && !options.containsKey(selected)) {
      if (!_countryId.hasMatch(selected)) return null;
      options[selected] = '${countryFlagFromCode(selected)} ${context.l10n.selectYourCountry}';
    }
    return options;
  }

  Widget _buildLogos() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const SizedBox(width: 18),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
          child: Image.asset(Assets.images.herologo.path, width: 26, color: OmiColors.onAccent),
        ),
        Transform.translate(
          offset: const Offset(-18, 0),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
            child: SvgPicture.asset(
              Assets.images.stripeLogo,
              width: 40,
              colorFilter: ColorFilter.mode(OmiColors.textPrimary, BlendMode.srcIn),
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
                    Icon(Icons.arrow_drop_down, color: OmiColors.textPrimary),
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
          decoration: BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.smAll),
          child: Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: OmiColors.danger, size: 20),
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
          launchUrl(Uri.parse(_stripeAgreementUrl));
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
      const _PollingPulse(),
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
              decoration: BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
              child: Icon(Icons.check_circle_outline_rounded, color: OmiColors.success, size: 48),
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
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
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

/// The classic polling indicator. It owns its animation so nothing ticks while the native
/// surface (or any other section) is showing.
class _PollingPulse extends StatefulWidget {
  const _PollingPulse();

  @override
  State<_PollingPulse> createState() => _PollingPulseState();
}

class _PollingPulseState extends State<_PollingPulse> with SingleTickerProviderStateMixin {
  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
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
          child: Center(child: Icon(Icons.sync, color: OmiColors.accent, size: 40)),
        );
      },
    );
  }
}
