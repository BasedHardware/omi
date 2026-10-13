import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The affiliate site's popup-based Google signup needs a system browser.
class ReferralPage extends StatefulWidget {
  const ReferralPage({super.key});

  @override
  State<ReferralPage> createState() => _ReferralPageState();
}

class _ReferralPageState extends State<ReferralPage> {
  bool _opening = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.pageOpened('Referral Program');
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
      () async => 'https://affiliate.omi.me/',
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
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.referralProgram)),
      body: SafeArea(
        child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: constraints.maxHeight),
                    child: _failed
                        ? OmiErrorState(
                            message: context.l10n.failedToStartAuth(context.l10n.referralProgram),
                            onRetry: _openBrowser)
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
                )),
      ),
    );
  }
}
