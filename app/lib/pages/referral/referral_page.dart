import 'dart:async';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/referrals.dart';
import 'package:omi/pages/apps/widgets/omi_external_browser_page.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// A request owns its authenticated session until the link is used, not just
/// until the HTTP response arrives. No referral URL is persisted.
class ReferralLinkSession {
  const ReferralLinkSession({required this.load, required this.isCurrent, this.claim});
  final Future<ReferralCampaign> Function() load;
  final Future<ReferralCampaign> Function()? claim;
  final bool Function() isCurrent;
}

ReferralLinkSession _authenticatedSession() {
  final auth = AuthService.instance;
  final snapshot = auth.captureSessionSnapshot();
  return ReferralLinkSession(
    load: () async {
      if (snapshot == null || !auth.isSessionSnapshotCurrent(snapshot)) throw StateError('No current account');
      return getReferralCampaign(session: snapshot);
    },
    claim: () async {
      if (snapshot == null || !auth.isSessionSnapshotCurrent(snapshot)) throw StateError('No current account');
      return getReferralCampaign(session: snapshot, claim: true);
    },
    isCurrent: () => snapshot != null && auth.isSessionSnapshotCurrent(snapshot),
  );
}

/// Host + path with the signed token shortened; copy and share always use the full link.
String referralShortLink(String url) {
  final uri = Uri.parse(url);
  final code = uri.pathSegments.isEmpty ? '' : uri.pathSegments.last;
  return code.length <= 8 ? '${uri.host}${uri.path}' : '${uri.host}/r/…${code.substring(code.length - 6)}';
}

class ReferralPage extends StatefulWidget {
  const ReferralPage({super.key, this.createSession, this.accountChanges, this.shareLink});
  final ReferralLinkSession Function()? createSession;
  final Stream<void>? accountChanges;
  final Future<void> Function(String, Rect)? shareLink;

  @override
  State<ReferralPage> createState() => _ReferralPageState();
}

class _ReferralPageState extends State<ReferralPage> with WidgetsBindingObserver {
  StreamSubscription<void>? _accountSubscription;
  ReferralLinkSession? _session;
  ReferralCampaign? _campaign;
  String? get _link => _campaign?.referralUrl;
  bool _loading = true;
  // An unreachable or old backend keeps the affiliate page; resumes must not reopen its browser.
  bool _fallback = false;
  bool _busy = false;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.pageOpened('Referral Program');
    if (!mobileReferralCampaignEnabled) return;
    WidgetsBinding.instance.addObserver(this);
    _accountSubscription = (widget.accountChanges ?? AuthService.instance.sessionGenerationEvents.map((_) {}))
        .listen((_) => _accountChanged());
    unawaited(_load());
  }

  void _accountChanged() {
    if (!mounted) return;
    final invalidation = ++_request;
    setState(() {
      _session = null;
      _busy = false;
      _fallback = false;
      _campaign = null;
      _loading = true;
    });
    // Auth generation events are synchronous. Capture only after the gateway
    // and the producer have finished their current transition.
    scheduleMicrotask(() {
      if (mounted && invalidation == _request) unawaited(_load());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed &&
        !_busy &&
        !_fallback &&
        (_campaign?.enabled != false || _session?.isCurrent() != true)) {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    final request = ++_request;
    final session = (widget.createSession ?? _authenticatedSession)();
    setState(() {
      _session = session;
      _campaign = null;
      _loading = true;
    });
    try {
      final link = await session.load().timeout(const Duration(seconds: 20));
      if (!mounted || request != _request) return;
      if (!session.isCurrent()) throw StateError('Account changed');
      setState(() => _campaign = link);
    } catch (_) {
      // Errors and old backends (404) fall back to the affiliate page. Never reuse a stale link.
      if (mounted && request == _request) _fallback = true;
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  Future<void> _useLink({required bool share, required BuildContext anchor}) async {
    if (_busy || _link == null) return;
    if (_session?.isCurrent() != true) {
      await _load();
      return;
    }
    final link = _link!;
    final request = _request;
    final box = anchor.findRenderObject() as RenderBox;
    final origin = box.localToGlobal(Offset.zero) & box.size;
    setState(() => _busy = true);
    try {
      if (share) {
        if (widget.shareLink != null) {
          await widget.shareLink!(link, origin);
        } else {
          await SharePlus.instance.share(ShareParams(text: link, sharePositionOrigin: origin));
        }
        // Dismissal is not a sent referral; there is no success toast/counter.
      } else {
        await OmiClipboard.copy(context, link);
      }
    } catch (_) {
      if (mounted && request == _request) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } finally {
      if (mounted && request == _request) setState(() => _busy = false);
    }
  }

  Future<void> _claim() async {
    final session = _session;
    if (_busy ||
        session == null ||
        session.claim == null ||
        _campaign?.enabled != true ||
        (_campaign?.claimableMonths ?? 0) == 0) {
      return;
    }
    if (!session.isCurrent()) {
      await _load();
      return;
    }
    final request = _request;
    setState(() => _busy = true);
    try {
      final result = await session.claim!().timeout(const Duration(seconds: 20));
      if (!mounted || request != _request || !session.isCurrent()) return;
      setState(() => _campaign = result);
    } catch (_) {
      if (mounted && request == _request && session.isCurrent()) {
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    } finally {
      if (mounted && request == _request) setState(() => _busy = false);
    }
  }

  Widget _rewardRow({required int start, required int need, required String title, required String detail}) {
    final campaign = _campaign!;
    final count = (campaign.milestoneProgress - start).clamp(0, need);
    final cumulative = start == 0 ? 2 : 5;
    final earned = count >= need || campaign.claimedMonths >= cumulative;
    // One claim takes every claimable month, so the pill sits on the first unclaimed earned row.
    final claimable = campaign.enabled &&
        campaign.claimableMonths > 0 &&
        earned &&
        campaign.claimedMonths < cumulative &&
        (start == 0 || campaign.claimedMonths >= 2);
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Row(children: [
        Container(
          key: Key('referral-reward-${start + need}${earned ? '-earned' : ''}'),
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: earned ? OmiColors.accent : null,
            border: Border.all(color: earned ? OmiColors.accent : OmiColors.surface3, width: 2),
          ),
          child: earned ? Icon(Icons.check, size: 14, color: OmiColors.onAccent) : null,
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            Text(detail, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          ]),
        ),
        const SizedBox(width: OmiSpacing.xs),
        if (claimable)
          OmiButton(
              key: const Key('referral-claim'),
              label: context.l10n.referralClaimShort,
              size: OmiButtonSize.compact,
              isLoading: _busy,
              onPressed: _busy ? null : _claim)
        else
          Text('$count/$need',
              style: OmiType.subhead
                  .copyWith(color: OmiColors.textTertiary, fontFeatures: const [FontFeature.tabularFigures()])),
      ]),
    );
  }

  @override
  void dispose() {
    ++_request;
    _accountSubscription?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Widget _affiliate(BuildContext context) => OmiExternalBrowserPage(
        title: context.l10n.referralProgram,
        url: Uri.parse('https://affiliate.omi.me/'),
        message: context.l10n.completeAuthInBrowser,
        openKey: const Key('referral-open-browser'),
      );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (!mobileReferralCampaignEnabled || (!_loading && _campaign?.enabled != true)) return _affiliate(context);
    if (_loading) {
      return Scaffold(
        appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.referralProgram)),
        body: const Center(child: OmiSpinner()),
      );
    }
    final campaign = _campaign!;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
          leading: const OmiBackButton(), title: Text(l10n.referralProgram), backgroundColor: OmiColors.surface0),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.xl),
          children: [
            Center(
              child: Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
                child: Icon(Icons.card_giftcard_outlined, size: 52, color: OmiColors.textPrimary),
              ),
            ),
            const SizedBox(height: OmiSpacing.lg),
            Text(l10n.referralCampaignTitle.replaceFirst('. ', '.\n'),
                textAlign: TextAlign.center, style: OmiType.title1.copyWith(height: 1.15)),
            const SizedBox(height: OmiSpacing.xs),
            Text(l10n.referralCampaignSubtitle.replaceFirst('. ', '.\n'),
                textAlign: TextAlign.center,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
            const SizedBox(height: OmiSpacing.xl),
            Container(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.xxs, OmiSpacing.xxs),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
              child: Row(children: [
                Expanded(
                  child: Text(referralShortLink(_link!),
                      key: const Key('referral-link'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ),
                Builder(
                    builder: (anchor) => OmiButton.secondary(
                          key: const Key('referral-copy'),
                          label: l10n.copy,
                          size: OmiButtonSize.compact,
                          onPressed: _busy ? null : () => _useLink(share: false, anchor: anchor),
                        )),
              ]),
            ),
            const SizedBox(height: OmiSpacing.sm),
            Builder(
                builder: (anchor) => OmiButton(
                      key: const Key('referral-share'),
                      label: l10n.referralShareInvite,
                      onPressed: _busy ? null : () => _useLink(share: true, anchor: anchor),
                      expand: true,
                    )),
            const SizedBox(height: OmiSpacing.xl),
            Padding(
              padding: const EdgeInsets.only(left: OmiSpacing.xxs, bottom: OmiSpacing.xs),
              child: Text(l10n.referralYourRewards.toUpperCase(),
                  style: OmiType.footnote
                      .copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600, letterSpacing: 0.4)),
            ),
            Container(
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
              child: Column(children: [
                _rewardRow(
                    start: 0, need: 2, title: l10n.referralRewardFirstTitle, detail: l10n.referralRewardFirstDetail),
                Divider(height: 1, thickness: 1, color: OmiColors.border),
                _rewardRow(
                    start: 2, need: 3, title: l10n.referralRewardSecondTitle, detail: l10n.referralRewardSecondDetail),
              ]),
            ),
            if (campaign.rewardStatus == 'pending_paid_subscription') ...[
              const SizedBox(height: OmiSpacing.xs),
              Text(l10n.referralRewardPending, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
            const SizedBox(height: OmiSpacing.xxl),
            Center(
              child: TextButton(
                key: const Key('referral-affiliate'),
                onPressed: () => routeToPage(context, _affiliate(context)),
                child: Text('${l10n.referralAffiliate} ›',
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
