import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/affiliate.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/referral/affiliate_views.dart';
import 'package:omi/services/integrations/integration_oauth.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The affiliate program, natively when the backend serves it for this account and through the
/// affiliate website otherwise.
class ReferralPage extends StatefulWidget {
  const ReferralPage({super.key, this.api = const AffiliateApi(), this.openUrl = openAffiliateUrl});

  final AffiliateApi api;
  final AffiliateUrlOpener openUrl;

  @override
  State<ReferralPage> createState() => _ReferralPageState();
}

class _ReferralPageState extends State<ReferralPage> {
  ApiResult<AffiliateStatus>? _status;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.pageOpened('Referral Program');
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _status = null);
    final result = await widget.api.status();
    if (mounted) setState(() => _status = result);
  }

  Future<void> _refresh() async {
    final result = await widget.api.status();
    if (mounted && result is ApiSuccess<AffiliateStatus>) setState(() => _status = result);
  }

  Widget _body(BuildContext context) {
    final l10n = context.l10n;
    switch (_status) {
      case null:
        return const OmiLoadingState();
      // An older backend has no affiliate routes; the website still serves everyone.
      case ApiFailure(problem: ApiProblem(kind: ApiProblemKind.notFound)):
        return const _AffiliateWebsiteHandoff();
      case ApiFailure():
        return OmiErrorState(message: l10n.affiliateLoadFailed, onRetry: _load);
      case ApiSuccess(:final data):
        switch (data.state) {
          case AffiliateState.unavailable:
            return const _AffiliateWebsiteHandoff();
          case AffiliateState.blocked:
            return OmiEmptyState(icon: Icons.block, title: l10n.referralProgram, message: l10n.affiliateBlocked);
          case AffiliateState.notLinked:
            return AffiliateJoinView(
              api: widget.api,
              status: data,
              openUrl: widget.openUrl,
              onLinked: (linked) => setState(() => _status = ApiSuccess(linked)),
            );
          case AffiliateState.linked:
            final profile = data.profile;
            if (profile == null) return OmiErrorState(message: l10n.affiliateLoadFailed, onRetry: _load);
            return AffiliateDashboard(
              key: ValueKey(profile.refCode),
              api: widget.api,
              profile: profile,
              openUrl: widget.openUrl,
              onRefreshStatus: _refresh,
            );
        }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.referralProgram)),
      body: SafeArea(child: _body(context)),
    );
  }
}

/// The affiliate site's popup-based Google signup needs a system browser.
class _AffiliateWebsiteHandoff extends StatefulWidget {
  const _AffiliateWebsiteHandoff();

  @override
  State<_AffiliateWebsiteHandoff> createState() => _AffiliateWebsiteHandoffState();
}

class _AffiliateWebsiteHandoffState extends State<_AffiliateWebsiteHandoff> {
  bool _opening = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_openBrowser());
    });
  }

  Future<void> _openBrowser() async {
    if (_opening) return;
    setState(() {
      _opening = true;
      _failed = false;
    });
    final opened = await launchIntegrationOAuth(
      () async => affiliateWebsiteUrl,
      deadline: const Duration(seconds: 15),
    );
    if (!mounted) return;
    setState(() {
      _opening = false;
      _failed = !opened;
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: _failed
              ? OmiErrorState(
                  message: context.l10n.failedToStartAuth(context.l10n.referralProgram),
                  onRetry: _openBrowser,
                )
              : OmiEmptyState(
                  icon: Icons.open_in_browser,
                  title: context.l10n.referralProgram,
                  message: context.l10n.completeAuthInBrowser,
                  action: OmiButton(
                    key: const Key('referral-open-browser'),
                    label: context.l10n.open,
                    isLoading: _opening,
                    onPressed: _openBrowser,
                  ),
                ),
        ),
      ),
    );
  }
}
