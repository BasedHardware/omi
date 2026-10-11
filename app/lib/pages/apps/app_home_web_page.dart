import 'dart:math';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/browser.dart';
import 'package:omi/widgets/extensions/string.dart';

/// An enabled app's own home page (its settings and dashboard), pushed from the app's detail page.
class AppHomeWebPage extends StatelessWidget {
  final App app;

  const AppHomeWebPage({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    final url = Uri.tryParse(
      appSetupUrlWithUid(app.externalIntegration?.appHomeUrl ?? '', SharedPreferencesUtil().uid),
    );
    // A malformed app-provided URL gets the page's error state, not a crash in build.
    if (url == null || !url.hasScheme) {
      return Scaffold(
        appBar: AppBar(leading: const OmiBackButton(), title: Text(app.name.decodeString)),
        body: OmiErrorState(message: context.l10n.couldNotLoadPage),
      );
    }
    return OmiWebPage(
      title: app.name.decodeString,
      url: url,
      userAgent: topUserAgents[Random().nextInt(topUserAgents.length)],
    );
  }
}
