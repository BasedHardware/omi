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
  const ReferralLinkSession({required this.load, required this.isCurrent});
  final Future<String> Function() load;
  final bool Function() isCurrent;
}

ReferralLinkSession _authenticatedSession() {
  final auth = AuthService.instance;
  final snapshot = auth.captureSessionSnapshot();
  return ReferralLinkSession(
    load: () async {
      if (snapshot == null || !auth.isSessionSnapshotCurrent(snapshot)) throw StateError('No current account');
      return getReferralLink(session: snapshot);
    },
    isCurrent: () => snapshot != null && auth.isSessionSnapshotCurrent(snapshot),
  );
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
  String? _link;
  bool _loading = true;
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
      _link = null;
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
    if (state == AppLifecycleState.resumed && _session?.isCurrent() != true) unawaited(_load());
  }

  Future<void> _load() async {
    final request = ++_request;
    final session = (widget.createSession ?? _authenticatedSession)();
    setState(() {
      _session = session;
      _link = null;
      _loading = true;
    });
    try {
      final link = await session.load().timeout(const Duration(seconds: 20));
      if (!mounted || request != _request) return;
      if (!session.isCurrent()) throw StateError('Account changed');
      setState(() => _link = link);
    } catch (_) {
      // Errors stay on this page with an explicit retry. Never reuse a stale link.
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
      if (mounted) setState(() => _busy = false);
    }
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
    if (!mobileReferralCampaignEnabled) return _affiliate(context);
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.referralProgram)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 16),
            const Icon(Icons.card_giftcard, size: 44),
            const SizedBox(height: 20),
            Text(l10n.referralGiftTitle, textAlign: TextAlign.center, style: OmiType.title1),
            const SizedBox(height: 24),
            Text(l10n.referralWebSteps, style: OmiType.callout.copyWith(height: 1.6, color: OmiColors.textSecondary)),
            const SizedBox(height: 24),
            if (_loading)
              const Center(child: OmiSpinner())
            else if (_link == null)
              OmiErrorState(message: l10n.somethingWentWrong, onRetry: _load)
            else ...[
              Text(_link!,
                  key: const Key('referral-link'),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: OmiColors.textSecondary)),
              const SizedBox(height: 16),
              Builder(
                  builder: (anchor) => OmiButton(
                        key: const Key('referral-share'),
                        label: l10n.share,
                        icon: Icons.ios_share,
                        onPressed: _busy ? null : () => _useLink(share: true, anchor: anchor),
                        expand: true,
                      )),
              Builder(
                  builder: (anchor) => OmiButton.tertiary(
                        key: const Key('referral-copy'),
                        label: l10n.copyLink,
                        onPressed: _busy ? null : () => _useLink(share: false, anchor: anchor),
                        expand: true,
                      )),
            ],
            const SizedBox(height: 24),
            const Divider(),
            OmiButton.tertiary(
              key: const Key('referral-affiliate'),
              label: l10n.referralAffiliate,
              icon: Icons.open_in_new,
              onPressed: () => routeToPage(context, _affiliate(context)),
              expand: true,
            ),
          ],
        ),
      ),
    );
  }
}
