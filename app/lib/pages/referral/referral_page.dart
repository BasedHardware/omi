import 'dart:async';

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/referrals.dart';
import 'package:omi/pages/apps/widgets/omi_external_browser_page.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
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

  Widget _milestone({required int start, required int need, required String title, required String detail}) {
    final campaign = _campaign!;
    final count = (campaign.milestoneProgress - start).clamp(0, need);
    final cumulative = start == 0 ? 2 : 5;
    final earned = count >= need || campaign.claimedMonths >= cumulative;
    final last = start != 0;
    // One claim takes every claimable month, so the pill sits on the first unclaimed earned row.
    final claimable = campaign.enabled &&
        campaign.claimableMonths > 0 &&
        earned &&
        campaign.claimedMonths < cumulative &&
        (start == 0 || campaign.claimedMonths >= 2);
    // At large text a pill beside the copy leaves too narrow a column and breaks words, so it moves under the detail.
    final bodySize = OmiType.body.fontSize!;
    final stackClaim = MediaQuery.textScalerOf(context).scale(bodySize) > bodySize * 1.3;
    final claim = OmiButton(
        key: const Key('referral-claim'),
        label: context.l10n.referralClaimShort,
        size: OmiButtonSize.compact,
        isLoading: _busy,
        onPressed: _busy ? null : _claim);
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(
          width: 26,
          child: Column(children: [
            const SizedBox(height: 2),
            Container(
              key: Key('referral-reward-${start + need}${earned ? '-earned' : ''}'),
              width: 26,
              height: 26,
              decoration: earned ? BoxDecoration(shape: BoxShape.circle, color: OmiColors.accent) : null,
              child: earned
                  ? Icon(Icons.check, size: 15, color: OmiColors.onAccent)
                  : CustomPaint(painter: _DashedCircle(OmiColors.surface3)),
            ),
            if (!last) Expanded(child: Center(child: Container(width: 2, color: OmiColors.surface3))),
          ]),
        ),
        const SizedBox(width: OmiSpacing.md),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: last ? 0 : OmiSpacing.xl),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: OmiType.body),
              const SizedBox(height: 2),
              Text(detail, style: OmiType.body.copyWith(color: OmiColors.textTertiary)),
              if (claimable && stackClaim) ...[const SizedBox(height: OmiSpacing.sm), claim],
            ]),
          ),
        ),
        if (claimable && !stackClaim) Align(alignment: Alignment.topCenter, child: claim),
      ]),
    );
  }

  // One copy button for assistive tech: the QR and avatar are decorative, and qr_flutter's own
  // label is hardcoded English.
  Widget _qrCard() => Builder(builder: (anchor) {
        final copy = _busy ? null : () => _useLink(share: false, anchor: anchor);
        return Semantics(
          key: const Key('referral-copy'),
          button: true,
          enabled: copy != null,
          label: context.l10n.copyLink,
          onTap: copy,
          excludeSemantics: true,
          child: GestureDetector(
            onTap: copy,
            child: Container(
              key: const Key('referral-link'),
              padding: const EdgeInsets.all(OmiSpacing.md),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: OmiRadius.lgAll,
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 24, offset: const Offset(0, 6))
                ],
              ),
              child: Stack(alignment: Alignment.center, children: [
                QrImageView(
                  key: ValueKey('referral-qr:$_link'),
                  data: _link!,
                  size: 204,
                  padding: EdgeInsets.zero,
                  backgroundColor: Colors.white,
                  errorCorrectionLevel: QrErrorCorrectLevel.M,
                  eyeStyle: const QrEyeStyle(eyeShape: QrEyeShape.square, color: Colors.black),
                  dataModuleStyle:
                      const QrDataModuleStyle(dataModuleShape: QrDataModuleShape.circle, color: Colors.black),
                ),
                Container(
                  width: 60,
                  height: 60,
                  padding: const EdgeInsets.all(5),
                  decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                  child: Container(
                    // The QR card stays white in dark mode, so the badge uses the light palette.
                    decoration: BoxDecoration(color: OmiPalette.light.surface2, shape: BoxShape.circle),
                    child: Icon(Icons.account_circle, size: 30, color: OmiPalette.light.textSecondary),
                  ),
                ),
              ]),
            ),
          ),
        );
      });

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
      backgroundColor: OmiColors.surface1,
      // Share sits in the bottom bar slot, so the Scaffold floats every toast above it at any text
      // size (UX contract §6); a copy confirmation or error never covers it.
      bottomNavigationBar: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.md),
          child: Builder(
            builder: (anchor) => OmiButton(
              key: const Key('referral-share'),
              label: l10n.share,
              icon: Icons.ios_share,
              expand: true,
              pill: true,
              height: 56,
              maxLines: null,
              isLoading: _busy,
              onPressed: _busy ? null : () => _useLink(share: true, anchor: anchor),
            ),
          ),
        ),
      ),
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(0, OmiSpacing.xs, OmiSpacing.md, 0),
              child: Material(
                color: OmiColors.surface1,
                shape: const CircleBorder(),
                elevation: 3,
                shadowColor: Colors.black.withValues(alpha: 0.25),
                child: IconButton(
                  key: const Key('referral-close'),
                  tooltip: MaterialLocalizations.of(context).closeButtonTooltip,
                  icon: Icon(Icons.close, color: OmiColors.textPrimary),
                  onPressed: () => Navigator.of(context).maybePop(),
                ),
              ),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.xl),
              child: Column(children: [
                Center(child: _qrCard()),
                const SizedBox(height: OmiSpacing.xxl),
                Text(l10n.referralCampaignTitle.replaceFirst('. ', '.\n'),
                    textAlign: TextAlign.center,
                    style: OmiType.largeTitle.copyWith(height: 1.12, letterSpacing: -0.6, fontWeight: FontWeight.w800)),
                const SizedBox(height: OmiSpacing.md),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
                  child: Text(l10n.referralCampaignSubtitle,
                      textAlign: TextAlign.center,
                      style: OmiType.body.copyWith(color: OmiColors.textTertiary, height: 1.45)),
                ),
                const SizedBox(height: OmiSpacing.xl + OmiSpacing.md),
                Container(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.lg, OmiSpacing.xl),
                  decoration: BoxDecoration(color: OmiColors.surface0, borderRadius: OmiRadius.xlAll),
                  child: Column(children: [
                    _milestone(
                        start: 0,
                        need: 2,
                        title: l10n.referralRewardFirstTitle,
                        detail: l10n.referralRewardFirstDetail),
                    _milestone(
                        start: 2,
                        need: 3,
                        title: l10n.referralRewardSecondTitle,
                        detail: l10n.referralRewardSecondDetail),
                  ]),
                ),
                if (campaign.rewardStatus == 'pending_paid_subscription') ...[
                  const SizedBox(height: OmiSpacing.sm),
                  Text(l10n.referralRewardPending,
                      textAlign: TextAlign.center, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ],
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

class _DashedCircle extends CustomPainter {
  const _DashedCircle(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final rect = Offset.zero & size;
    const dashes = 12;
    const sweep = 2 * 3.141592653589793 / dashes;
    for (var i = 0; i < dashes; i++) {
      canvas.drawArc(rect.deflate(1), i * sweep, sweep * 0.6, false, paint);
    }
  }

  @override
  bool shouldRepaint(_DashedCircle old) => old.color != color;
}
