import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/affiliate.dart';
import 'package:omi/backend/http/api/payments.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/affiliate_wire.g.dart' as wire;
import 'package:omi/services/integrations/integration_oauth.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_sheet.dart';

const affiliateWebsiteUrl = 'https://affiliate.omi.me/';

typedef AffiliateUrlOpener = Future<bool> Function(String url);

Future<bool> openAffiliateUrl(String url) => launchIntegrationOAuth(() async => url);

String _money(BuildContext context, double? amount, String? currency) {
  final format = NumberFormat.simpleCurrency(
    locale: Localizations.localeOf(context).toString(),
    name: (currency ?? 'USD').toUpperCase(),
  );
  return format.format(amount ?? 0);
}

String _actionError(BuildContext context, ApiProblem problem) {
  final l10n = context.l10n;
  return switch (problem.kind) {
    ApiProblemKind.rateLimited => l10n.affiliateTooManyAttempts,
    _ => l10n.affiliateActionFailed,
  };
}

TextField _field(
  BuildContext context, {
  required TextEditingController controller,
  required String hint,
  bool obscure = false,
  TextInputType? keyboard,
  Iterable<String>? autofill,
  bool enabled = true,
  ValueChanged<String>? onSubmitted,
  ValueChanged<String>? onChanged,
}) =>
    TextField(
      controller: controller,
      obscureText: obscure,
      enabled: enabled,
      keyboardType: keyboard,
      autofillHints: autofill,
      autocorrect: false,
      onSubmitted: onSubmitted,
      onChanged: onChanged,
      style: OmiType.body,
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
        filled: true,
        fillColor: OmiColors.surface2,
        contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
        border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
        enabledBorder: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
        focusedBorder: OutlineInputBorder(
          borderRadius: OmiRadius.mdAll,
          borderSide: BorderSide(color: OmiColors.textTertiary),
        ),
      ),
    );

class _Steps extends StatelessWidget {
  const _Steps();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final steps = [l10n.affiliateStep1, l10n.affiliateStep2, l10n.affiliateStep3];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.affiliateHowItWorks, style: OmiType.headline),
        const SizedBox(height: OmiSpacing.sm),
        for (var i = 0; i < steps.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 24,
                  height: 24,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                  child: Text('${i + 1}', style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600)),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(steps[i], style: OmiType.subhead.copyWith(color: OmiColors.textSecondary))),
              ],
            ),
          ),
      ],
    );
  }
}

// ----------------------------------------------------------------------------- not linked

class AffiliateJoinView extends StatefulWidget {
  const AffiliateJoinView({
    super.key,
    required this.api,
    required this.status,
    required this.onLinked,
    this.openUrl = openAffiliateUrl,
  });

  final AffiliateApi api;
  final AffiliateStatus status;
  final ValueChanged<AffiliateStatus> onLinked;
  final AffiliateUrlOpener openUrl;

  @override
  State<AffiliateJoinView> createState() => _AffiliateJoinViewState();
}

class _AffiliateJoinViewState extends State<AffiliateJoinView> {
  bool _busy = false;

  Future<void> _run(Future<ApiResult<AffiliateStatus>> Function() action, String method) async {
    if (_busy) return;
    setState(() => _busy = true);
    final result = await action();
    if (!mounted) return;
    setState(() => _busy = false);
    switch (result) {
      case ApiSuccess(:final data):
        PlatformManager.instance.analytics.track('Affiliate Linked', properties: {'method': method});
        widget.onLinked(data);
      case ApiFailure(:final problem):
        final l10n = context.l10n;
        final message = switch (problem.statusCode) {
          403 when method == 'joined' => l10n.affiliateEmailNotVerified,
          409 => l10n.affiliateAlreadyLinked,
          _ => _actionError(context, problem),
        };
        OmiFeedback.error(context, message);
    }
  }

  Future<void> _signIn() async {
    final linked = await showOmiSheet<AffiliateStatus>(
      context: context,
      title: context.l10n.affiliateConnectAccount,
      builder: (_) => AffiliateCredentialsSheet(api: widget.api),
    );
    if (linked != null && mounted) {
      PlatformManager.instance.analytics.track('Affiliate Linked', properties: {'method': 'affiliate_login'});
      widget.onLinked(linked);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final emailMatch = widget.status.emailMatchAvailable;
    return ListView(
      padding: const EdgeInsets.all(OmiSpacing.md),
      children: [
        const SizedBox(height: OmiSpacing.md),
        Text(l10n.affiliateJoinTitle, style: OmiType.title1),
        const SizedBox(height: OmiSpacing.xs),
        Text(l10n.affiliateSubtitle, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
        const SizedBox(height: OmiSpacing.xl),
        const _Steps(),
        const SizedBox(height: OmiSpacing.lg),
        if (emailMatch) ...[
          Text(l10n.affiliateEmailMatchMessage, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
            key: const Key('affiliate-connect-email'),
            label: l10n.affiliateConnectAccount,
            expand: true,
            isLoading: _busy,
            onPressed: () => _run(widget.api.linkByEmail, 'email_match'),
          ),
        ] else ...[
          OmiButton(
            key: const Key('affiliate-join'),
            label: l10n.affiliateJoin,
            expand: true,
            isLoading: _busy,
            onPressed: () => _run(widget.api.join, 'joined'),
          ),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.secondary(
            key: const Key('affiliate-sign-in'),
            label: l10n.affiliateHaveAccount,
            expand: true,
            onPressed: _busy ? null : () => unawaited(_signIn()),
          ),
        ],
        const SizedBox(height: OmiSpacing.xs),
        OmiButton.tertiary(
          label: l10n.affiliateFullDashboard,
          expand: true,
          onPressed: () => widget.openUrl(affiliateWebsiteUrl),
        ),
      ],
    );
  }
}

class AffiliateCredentialsSheet extends StatefulWidget {
  const AffiliateCredentialsSheet({super.key, required this.api});

  final AffiliateApi api;

  @override
  State<AffiliateCredentialsSheet> createState() => _AffiliateCredentialsSheetState();
}

class _AffiliateCredentialsSheetState extends State<AffiliateCredentialsSheet> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  bool get _canSubmit => !_busy && _email.text.trim().contains('@') && _password.text.isNotEmpty;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final result = await widget.api.linkWithCredentials(_email.text.trim(), _password.text);
    if (!mounted) return;
    switch (result) {
      case ApiSuccess(:final data):
        Navigator.of(context).pop(data);
      case ApiFailure(:final problem):
        final l10n = context.l10n;
        setState(() {
          _busy = false;
          _error = switch (problem.statusCode) {
            400 => l10n.affiliateWrongPassword,
            409 => l10n.affiliateAlreadyLinked,
            403 => l10n.affiliateBlocked,
            _ => _actionError(context, problem),
          };
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return AutofillGroup(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.affiliateSignInMessage, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.md),
          _field(
            context,
            controller: _email,
            hint: l10n.email,
            keyboard: TextInputType.emailAddress,
            autofill: const [AutofillHints.email, AutofillHints.username],
            enabled: !_busy,
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: OmiSpacing.xs),
          _field(
            context,
            controller: _password,
            hint: l10n.password,
            obscure: true,
            autofill: const [AutofillHints.password],
            enabled: !_busy,
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => _submit(),
          ),
          if (_error != null) ...[
            const SizedBox(height: OmiSpacing.sm),
            Semantics(
              liveRegion: true,
              child: Text(_error!, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
          OmiButton(
            key: const Key('affiliate-credentials-submit'),
            label: l10n.connect,
            expand: true,
            isLoading: _busy,
            onPressed: _canSubmit ? _submit : null,
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

// ----------------------------------------------------------------------------- linked

class AffiliateDashboard extends StatefulWidget {
  const AffiliateDashboard({
    super.key,
    required this.api,
    required this.profile,
    required this.onRefreshStatus,
    this.openUrl = openAffiliateUrl,
  });

  final AffiliateApi api;
  final wire.GeneratedAffiliateProfile profile;
  final Future<void> Function() onRefreshStatus;
  final AffiliateUrlOpener openUrl;

  @override
  State<AffiliateDashboard> createState() => _AffiliateDashboardState();
}

class _AffiliateDashboardState extends State<AffiliateDashboard> with WidgetsBindingObserver {
  final _shareKey = GlobalKey();
  wire.GeneratedAffiliateStatsResponse? _stats;
  wire.GeneratedAffiliateOrdersResponse? _orders;
  wire.GeneratedAffiliateEarningsResponse? _earnings;
  wire.GeneratedAffiliatePayoutAccountStatusResponse? _payoutAccount;
  bool _loading = true;
  bool _failed = false;
  bool _openingPayouts = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // Returning from Stripe onboarding in the browser: show the new payout state.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_loadPayoutAccount());
  }

  Future<void> _loadPayoutAccount() async {
    final result = await widget.api.payoutAccount();
    if (mounted && result is ApiSuccess<wire.GeneratedAffiliatePayoutAccountStatusResponse>) {
      setState(() => _payoutAccount = result.data);
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = _stats == null;
      _failed = false;
    });
    final results = await Future.wait([
      widget.api.stats(),
      widget.api.orders(limit: 5),
      widget.api.earnings(),
      widget.api.payoutAccount(),
    ]);
    if (!mounted) return;
    final stats = results[0];
    setState(() {
      _loading = false;
      if (stats is ApiSuccess<wire.GeneratedAffiliateStatsResponse>) {
        _stats = stats.data;
      } else {
        _failed = _stats == null;
      }
      final orders = results[1];
      if (orders is ApiSuccess<wire.GeneratedAffiliateOrdersResponse>) _orders = orders.data;
      final earnings = results[2];
      if (earnings is ApiSuccess<wire.GeneratedAffiliateEarningsResponse>) _earnings = earnings.data;
      final payout = results[3];
      if (payout is ApiSuccess<wire.GeneratedAffiliatePayoutAccountStatusResponse>) _payoutAccount = payout.data;
    });
  }

  String? _rate(BuildContext context) {
    final standard = _earnings?.commissions.where((c) => c.standard).firstOrNull;
    final value = standard?.commissionValue;
    if (value == null) return null;
    if (standard!.commissionType == 'percentage') {
      return '${NumberFormat.decimalPattern(Localizations.localeOf(context).toString()).format(value)}%';
    }
    return _money(context, value, null);
  }

  Future<void> _share() async {
    final url = widget.profile.referralUrl;
    if (url == null) return;
    OmiHaptics.light();
    await SharePlus.instance.share(
      ShareParams(text: context.l10n.affiliateShareMessage(url), sharePositionOrigin: shareSheetOrigin(_shareKey)),
    );
    PlatformManager.instance.analytics.track('Affiliate Link Shared');
  }

  Future<void> _changeCode() async {
    final updated = await showOmiSheet<String>(
      context: context,
      title: context.l10n.affiliateChangeCode,
      builder: (_) => AffiliateRefCodeSheet(api: widget.api, current: widget.profile.refCode ?? ''),
    );
    if (updated != null && mounted) {
      OmiFeedback.confirm(context, context.l10n.affiliateCodeUpdated);
      await widget.onRefreshStatus();
    }
  }

  Future<void> _openPayouts({required bool dashboard}) async {
    if (_openingPayouts) return;
    String? country;
    if (!dashboard && !(_payoutAccount?.hasAccount ?? false)) {
      country = await showOmiSheet<String>(
        context: context,
        title: context.l10n.affiliateCountryTitle,
        builder: (_) => const AffiliateCountrySheet(),
      );
      if (country == null || !mounted) return;
    }
    setState(() => _openingPayouts = true);
    final result =
        dashboard ? await widget.api.payoutDashboardLink() : await widget.api.payoutSetupLink(country: country);
    if (!mounted) return;
    setState(() => _openingPayouts = false);
    switch (result) {
      case ApiSuccess(:final data):
        if (!dashboard) PlatformManager.instance.analytics.track('Affiliate Payout Setup Started');
        if (!await widget.openUrl(data) && mounted) OmiFeedback.error(context, context.l10n.affiliateActionFailed);
      case ApiFailure(:final problem):
        OmiFeedback.error(context, _actionError(context, problem));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (_loading) return const OmiLoadingState();
    if (_failed) return OmiErrorState(message: l10n.affiliateLoadFailed, onRetry: _load);
    final rate = _rate(context);
    return RefreshIndicator(
      onRefresh: () async {
        await widget.onRefreshStatus();
        await _load();
      },
      child: ListView(
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          Text(l10n.affiliateHeadline, style: OmiType.title1),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            rate == null ? l10n.affiliateSubtitle : l10n.affiliateCommissionRate(rate),
            style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.lg),
          _linkCard(context),
          const SizedBox(height: OmiSpacing.lg),
          _statsGrid(context),
          const SizedBox(height: OmiSpacing.lg),
          _ordersSection(context),
          const SizedBox(height: OmiSpacing.lg),
          _payoutsSection(context),
          const SizedBox(height: OmiSpacing.md),
          const _Steps(),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.tertiary(
            label: l10n.affiliateFullDashboard,
            expand: true,
            onPressed: () => widget.openUrl(affiliateWebsiteUrl),
          ),
          const SizedBox(height: OmiSpacing.lg),
        ],
      ),
    );
  }

  Widget _copyRow(BuildContext context, {required String label, required String value, required Key key}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        const SizedBox(height: OmiSpacing.xxs),
        Container(
          constraints: const BoxConstraints(minHeight: 48),
          padding: const EdgeInsets.only(left: OmiSpacing.sm),
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
          child: Row(
            children: [
              Expanded(
                child: Text(value, style: OmiType.subhead, maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
              OmiButton.tertiary(
                key: key,
                label: context.l10n.copy,
                size: OmiButtonSize.compact,
                onPressed: () => OmiClipboard.copy(context, value, what: label),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _linkCard(BuildContext context) {
    final l10n = context.l10n;
    final url = widget.profile.referralUrl;
    final coupon = widget.profile.coupon;
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (url != null)
            _copyRow(context, label: l10n.affiliateYourLink, value: url, key: const Key('affiliate-copy-link')),
          if (coupon != null) ...[
            const SizedBox(height: OmiSpacing.sm),
            _copyRow(context, label: l10n.affiliateYourCoupon, value: coupon, key: const Key('affiliate-copy-coupon')),
          ],
          const SizedBox(height: OmiSpacing.md),
          OmiButton(
            key: _shareKey,
            label: l10n.affiliateShareLink,
            icon: Icons.ios_share,
            expand: true,
            onPressed: url == null ? null : _share,
          ),
          const SizedBox(height: OmiSpacing.xxs),
          OmiButton.tertiary(
            key: const Key('affiliate-change-code'),
            label: l10n.affiliateChangeCode,
            expand: true,
            onPressed: () => unawaited(_changeCode()),
          ),
        ],
      ),
    );
  }

  Widget _statsGrid(BuildContext context) {
    final l10n = context.l10n;
    final stats = _stats!;
    final currency = _orders?.orders.map((o) => o.currency).whereType<String>().firstOrNull;
    final tiles = [
      (l10n.affiliateEarned, _money(context, stats.totalCommission, currency)),
      (l10n.affiliatePaidOut, _money(context, stats.paidCommission, currency)),
      (l10n.affiliateOrders, NumberFormat.decimalPattern().format(stats.totalOrders)),
      (l10n.affiliateClicks, NumberFormat.decimalPattern().format(stats.totalClicks)),
    ];
    Widget tile((String, String) entry) => Expanded(
          child: Semantics(
            label: '${entry.$1}: ${entry.$2}',
            excludeSemantics: true,
            child: Container(
              padding: const EdgeInsets.all(OmiSpacing.md),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(entry.$2, style: OmiType.title2, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: OmiSpacing.xxs),
                  Text(entry.$1, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ],
              ),
            ),
          ),
        );
    return Column(
      children: [
        Row(children: [tile(tiles[0]), const SizedBox(width: OmiSpacing.xs), tile(tiles[1])]),
        const SizedBox(height: OmiSpacing.xs),
        Row(children: [tile(tiles[2]), const SizedBox(width: OmiSpacing.xs), tile(tiles[3])]),
      ],
    );
  }

  Widget _ordersSection(BuildContext context) {
    final l10n = context.l10n;
    final orders = _orders?.orders ?? const <wire.GeneratedAffiliateOrder>[];
    final dates = OmiDateFormat.of(context);
    return OmiSettingsGroup(
      header: l10n.affiliateRecentOrders,
      children: orders.isEmpty
          ? [OmiSettingsRow(title: l10n.affiliateNoOrders)]
          : [
              for (final order in orders)
                OmiSettingsRow(
                  title: order.number ?? order.id,
                  subtitle: switch (DateTime.tryParse(order.createdAt ?? '')) {
                    final DateTime at => dates.date(at.toLocal()),
                    null => null,
                  },
                  value: _money(context, order.commission, order.currency),
                ),
            ],
    );
  }

  Widget _payoutsSection(BuildContext context) {
    final l10n = context.l10n;
    final account = _payoutAccount;
    final OmiSettingsRow row;
    if (account == null || !account.hasAccount) {
      row = OmiSettingsRow(
        title: l10n.affiliateSetUpPayouts,
        subtitle: l10n.affiliatePayoutsSetupMessage,
        leading: const Icon(Icons.account_balance_outlined),
        trailing: _openingPayouts ? const OmiSpinner() : null,
        onTap: () => _openPayouts(dashboard: false),
      );
    } else if (!account.connected || account.hasIssues) {
      row = OmiSettingsRow(
        title: l10n.affiliateFinishSetup,
        subtitle: l10n.affiliatePayoutsNeedAttention,
        leading: Icon(Icons.error_outline, color: OmiColors.warning),
        trailing: _openingPayouts ? const OmiSpinner() : null,
        onTap: () => _openPayouts(dashboard: false),
      );
    } else {
      row = OmiSettingsRow(
        title: l10n.affiliateOpenStripe,
        subtitle: l10n.affiliatePayoutsActive,
        leading: Icon(Icons.check_circle_outline, color: OmiColors.success),
        trailing: _openingPayouts ? const OmiSpinner() : null,
        onTap: () => _openPayouts(dashboard: true),
      );
    }
    return OmiSettingsGroup(header: l10n.affiliatePayouts, children: [row]);
  }
}

class AffiliateRefCodeSheet extends StatefulWidget {
  const AffiliateRefCodeSheet({super.key, required this.api, required this.current});

  final AffiliateApi api;
  final String current;

  @override
  State<AffiliateRefCodeSheet> createState() => _AffiliateRefCodeSheetState();
}

class _AffiliateRefCodeSheetState extends State<AffiliateRefCodeSheet> {
  late final _code = TextEditingController(text: widget.current.toLowerCase());
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final code = _code.text.trim();
    if (_busy || code.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final l10n = context.l10n;
    final check = await widget.api.checkRefCode(code);
    if (!mounted) return;
    if (check case ApiSuccess(:final data) when data.current) {
      Navigator.of(context).pop();
      return;
    }
    if (check case ApiSuccess(:final data) when !data.available) {
      setState(() {
        _busy = false;
        _error = l10n.affiliateCodeUnavailable;
      });
      return;
    }
    final result = await widget.api.updateRefCode(code);
    if (!mounted) return;
    switch (result) {
      case ApiSuccess(:final data):
        PlatformManager.instance.analytics.track('Affiliate Ref Code Changed');
        Navigator.of(context).pop(data.refCode);
      case ApiFailure(:final problem):
        setState(() {
          _busy = false;
          _error = switch (problem.statusCode) {
            400 || 409 => l10n.affiliateCodeUnavailable,
            _ => _actionError(context, problem),
          };
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _field(context,
            controller: _code, hint: l10n.affiliateChangeCode, enabled: !_busy, onSubmitted: (_) => _save()),
        const SizedBox(height: OmiSpacing.xs),
        Text(l10n.affiliateCodeHint, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        if (_error != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          Semantics(
            liveRegion: true,
            child: Text(_error!, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
          ),
        ],
        const SizedBox(height: OmiSpacing.md),
        OmiButton(
          key: const Key('affiliate-ref-code-save'),
          label: l10n.save,
          expand: true,
          isLoading: _busy,
          onPressed: _save,
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}

class AffiliateCountrySheet extends StatefulWidget {
  const AffiliateCountrySheet({super.key, this.loadCountries = getStripeSupportedCountries});

  final Future<List?> Function() loadCountries;

  @override
  State<AffiliateCountrySheet> createState() => _AffiliateCountrySheetState();
}

class _AffiliateCountrySheetState extends State<AffiliateCountrySheet> {
  List<(String, String)>? _countries;
  bool _failed = false;
  String _query = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _failed = false);
    final raw = await widget.loadCountries();
    if (!mounted) return;
    setState(() {
      if (raw == null) {
        _failed = true;
        return;
      }
      _countries = [
        for (final row in raw)
          if (row is Map && row['id'] is String && row['name'] is String) (row['id'] as String, row['name'] as String),
      ];
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final countries = _countries;
    final Widget body;
    if (_failed) {
      body = OmiErrorState(message: l10n.affiliateActionFailed, onRetry: _load);
    } else if (countries == null) {
      body = const OmiLoadingState();
    } else {
      final q = _query.toLowerCase();
      final shown = countries.where((c) => q.isEmpty || c.$2.toLowerCase().contains(q) || c.$1.toLowerCase() == q);
      body = ListView(
        children: [
          for (final country in shown)
            OmiSettingsRow(title: country.$2, onTap: () => Navigator.of(context).pop(country.$1)),
        ],
      );
    }
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.affiliateCountryMessage, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.sm),
          OmiSearchField(placeholder: l10n.affiliateSearchCountries, onChanged: (v) => setState(() => _query = v)),
          const SizedBox(height: OmiSpacing.sm),
          Expanded(child: body),
        ],
      ),
    );
  }
}
