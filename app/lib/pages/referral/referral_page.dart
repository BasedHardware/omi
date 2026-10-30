import 'package:flutter/material.dart';

import 'package:omi/pages/apps/widgets/omi_external_browser_page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class ReferralPage extends StatefulWidget {
  const ReferralPage({super.key});
  @override
  State<ReferralPage> createState() => _ReferralPageState();
}

class _ReferralPageState extends State<ReferralPage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.pageOpened('Referral Program');
  }

  @override
  Widget build(BuildContext context) => OmiExternalBrowserPage(
        title: context.l10n.referralProgram,
        url: Uri.parse('https://affiliate.omi.me/'),
        message: context.l10n.completeAuthInBrowser,
        openKey: const Key('referral-open-browser'),
      );
}
