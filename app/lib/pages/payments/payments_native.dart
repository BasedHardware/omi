part of 'payments_page.dart';

extension _NativePayments on _PaymentsPageState {
  /// The payout methods as native rows. Every action runs the classic card's closure, so the
  /// provider, StripeConnectSetup and analytics stay the owners; SF Symbols replace brand logos.
  Widget _nativePaymentsSurface(PaymentMethodProvider provider, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final active = _activeMethod(provider) != null;
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.payments,
        fallback: classic,
        loading: provider.isLoading,
        onRefresh: (_) => provider.getPaymentMethodsStatus(),
        toolbar: [
          NativeRow('payout_back', l10n.back,
              symbol: 'chevron.left', action: (_) async => await Navigator.of(context).maybePop()),
        ],
        sections: [
          NativeSection('payout_selected', title: l10n.selectedPaymentMethod, [
            if (!active)
              NativeRow('payout_info', l10n.connectPaymentMethodInfo, kind: 'label', symbol: 'info.circle')
            else ...[
              NativeRow('payout_active:stripe', l10n.paymentMethodStripe,
                  kind: 'label', subtitle: l10n.paymentStatusActive, symbol: 'checkmark.seal.fill'),
              NativeRow('payout_update:stripe', l10n.update,
                  symbol: 'arrow.triangle.2.circlepath', action: (_) => _manageActiveStripe()),
            ],
          ]),
          NativeSection('payout_available', title: l10n.availablePaymentMethods, [
            if (provider.isStripeConnected && !active)
              NativeRow('payout_method:stripe', l10n.paymentMethodStripe,
                  kind: 'menu',
                  subtitle: l10n.paymentStatusConnected,
                  symbol: 'creditcard',
                  options: {'update': l10n.update, 'set_active': l10n.setActive}, action: (value) {
                if (value == 'update') _manageStripe();
                if (value == 'set_active') _setStripeActive(provider);
              }),
            if (!provider.isStripeConnected)
              NativeRow('payout_connect:stripe', l10n.paymentMethodStripe,
                  kind: 'navigation',
                  subtitle: l10n.paymentStatusNotConnected,
                  symbol: 'creditcard',
                  action: (_) => _manageStripe()),
            NativeRow('payout_coming_soon', l10n.morePaymentMethodsComingSoon, kind: 'label', symbol: 'clock'),
          ]),
        ],
      ),
    );
  }
}
