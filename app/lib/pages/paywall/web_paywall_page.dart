import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Variant `web`: the paywall is a web page, so its layout, copy and order change over the air.
/// The page only renders; money moves through the same native checkout as every other paywall.
///
/// Bridge: the page posts JSON to the `OmiPaywall` channel —
/// `{"type":"ready"}`, `{"type":"checkout","interval":"year"|"month"}`, `{"type":"free"}`,
/// `{"type":"restore"}`, `{"type":"fallback"}` — and may define `window.OmiPaywallHost.onCheckout(outcome)`.
/// The URL carries `source`, `platform`, `locale`, `name`, `free_minutes`, `tier`, and per interval
/// `<interval>_amount` (minor units) and `<interval>_currency`.
///
/// Fail-open: a page that errors, 4xx/5xxs, or never reports ready within [loadTimeout] is replaced
/// by the native plans sheet, so a dead URL never costs a purchase.
class WebPaywallPage extends StatefulWidget {
  const WebPaywallPage({super.key, required this.source, required this.url});

  final String source;
  final Uri url;

  static const loadTimeout = Duration(seconds: 10);
  static const channel = 'OmiPaywall';

  /// The page URL for one reader; exposed for tests.
  static Uri buildUrl(
    Uri base, {
    required String source,
    required String platform,
    required String locale,
    required String name,
    required int freeMinutes,
    PaywallOffer? offer,
  }) {
    final params = Map<String, String>.from(base.queryParameters)
      ..['source'] = source
      ..['variant'] = 'web'
      ..['platform'] = platform
      ..['locale'] = locale
      ..['free_minutes'] = '$freeMinutes';
    if (name.isNotEmpty) params['name'] = name;
    if (offer != null) {
      params['tier'] = offer.tierId;
      for (final price in [offer.monthly, offer.yearly]) {
        if (price == null) continue;
        params['${price.interval}_amount'] = '${price.amountMinor}';
        params['${price.interval}_currency'] = price.currency;
      }
    }
    return base.replace(queryParameters: params);
  }

  @override
  State<WebPaywallPage> createState() => _WebPaywallPageState();
}

class _WebPaywallPageState extends State<WebPaywallPage> {
  WebViewController? _controller;
  Timer? _timeout;
  PaywallOffer? _offer;
  bool _ready = false;
  bool _closed = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _prepare());
  }

  @override
  void dispose() {
    _timeout?.cancel();
    super.dispose();
  }

  Future<void> _prepare() async {
    if (!mounted) return;
    final usage = context.read<UsageProvider>();
    if (usage.availablePlans == null) await usage.loadAvailablePlans();
    if (!mounted) return;
    final subscription = usage.subscription?.subscription;
    _offer = PaywallOffer.fromCatalog(
      usage.availablePlans,
      cancelAtPeriodEnd: subscription?.cancelAtPeriodEnd == true,
      currentPriceId: subscription?.currentPriceId,
    );
    final url = WebPaywallPage.buildUrl(
      widget.url,
      source: widget.source,
      platform: Platform.isIOS ? 'ios' : (Platform.isAndroid ? 'android' : 'other'),
      locale: Localizations.localeOf(context).toLanguageTag(),
      name: SharedPreferencesUtil().givenName,
      freeMinutes: (usage.subscription?.transcriptionSecondsLimit ?? 0) ~/ 60,
      offer: _offer,
    );
    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..addJavaScriptChannel(WebPaywallPage.channel, onMessageReceived: (message) => _onMessage(message.message))
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (request) =>
              request.url.startsWith('https://') ? NavigationDecision.navigate : NavigationDecision.prevent,
          onWebResourceError: (error) {
            if (error.isForMainFrame == false) return;
            Logger.debug('Web paywall load error: ${error.description}');
            _fallback(PaywallVariantFallbackReason.loadError);
          },
          onHttpError: (error) {
            final status = error.response?.statusCode ?? 0;
            if (status >= 400 && _isMainFrame(error.request?.uri)) {
              _fallback(PaywallVariantFallbackReason.loadError);
            }
          },
        ),
      );
    setState(() => _controller = controller);
    _timeout = Timer(WebPaywallPage.loadTimeout, () {
      if (!_ready) _fallback(PaywallVariantFallbackReason.timeout);
    });
    await controller.loadRequest(url);
  }

  /// Whether a failed request is the page itself rather than something it loads.
  bool _isMainFrame(Uri? uri) => uri == null || (uri.host == widget.url.host && uri.path == widget.url.path);

  Future<void> _onMessage(String raw) async {
    Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map) return;
    switch (decoded['type']) {
      case 'ready':
        _timeout?.cancel();
        if (mounted && !_ready) setState(() => _ready = true);
      case 'checkout':
        await _checkout(decoded['interval'] == 'month' ? 'month' : 'year');
      case 'free':
        _dismiss();
      case 'restore':
        await _restore();
      case 'fallback':
        _fallback(PaywallVariantFallbackReason.pageRequested);
    }
  }

  Future<void> _checkout(String interval) async {
    final offer = _offer;
    final price = interval == 'month' ? (offer?.monthly ?? offer?.yearly) : (offer?.yearly ?? offer?.monthly);
    if (offer == null || price == null || _busy || !mounted) {
      await _tell('onCheckout', 'unavailable');
      return;
    }
    _busy = true;
    try {
      final outcome = await PaywallCheckout.start(
        context,
        priceId: price.priceId,
        plan: offer.tierId,
        interval: price.interval,
        source: widget.source,
      );
      if (!mounted) return;
      await _tell('onCheckout', outcome.name);
      if (!mounted) return;
      if (outcome == PaywallCheckoutOutcome.purchased) {
        _closed = true;
        Navigator.of(context).pop(true);
      }
    } finally {
      _busy = false;
    }
  }

  Future<void> _tell(String method, String argument) async {
    final controller = _controller;
    if (controller == null) return;
    try {
      await controller.runJavaScript(
        'window.OmiPaywallHost && window.OmiPaywallHost.$method && window.OmiPaywallHost.$method(${jsonEncode(argument)})',
      );
    } catch (_) {}
  }

  Future<void> _restore() async {
    final usage = context.read<UsageProvider>();
    await usage.fetchSubscription();
    if (!mounted) return;
    if (usage.subscription?.subscription.plan.isPaid == true) {
      OmiFeedback.confirm(context, context.l10n.unlimitedPlan);
      _closed = true;
      Navigator.of(context).pop(true);
      return;
    }
    await _tell('onRestore', 'free');
  }

  void _dismiss() {
    if (_closed) return;
    _closed = true;
    PlatformManager.instance.analytics.upgradeModalDismissed();
    Navigator.of(context).pop(false);
  }

  /// Replaces this page with the native plans sheet (control) and records why.
  void _fallback(PaywallVariantFallbackReason reason) {
    if (_closed || !mounted) return;
    _closed = true;
    _timeout?.cancel();
    const TypedEvents().emit(PaywallVariantFallback(variant: PaywallVariantFallbackVariant.web, reason: reason));
    Navigator.of(context).pushReplacement(
      omiPageRoute(
        builder: (_) => UsagePage(showUpgradeDialog: true, paywallSource: widget.source, forceNativePaywall: true),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _dismiss();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(
          children: [
            if (controller != null) Positioned.fill(child: WebViewWidget(controller: controller)),
            if (!_ready) const Center(child: OmiSpinner(color: Colors.white)),
            Positioned(
              top: MediaQuery.paddingOf(context).top + 4,
              left: 4,
              child: IconButton(
                key: const Key('web_paywall_close'),
                tooltip: context.l10n.useFreePlan,
                onPressed: _dismiss,
                icon: const Icon(Icons.close, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
