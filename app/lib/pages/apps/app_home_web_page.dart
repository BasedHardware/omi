import 'dart:math';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/utils/browser.dart';
import 'package:omi/widgets/extensions/string.dart';

/// An enabled app's own home page (its settings and dashboard), pushed from the app's detail page.
class AppHomeWebPage extends StatelessWidget {
  final App app;

  const AppHomeWebPage({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    final url = appSetupUrlWithUid(app.externalIntegration?.appHomeUrl ?? '', SharedPreferencesUtil().uid);
    return OmiWebPage(
      title: app.name.decodeString,
      url: Uri.parse(url),
      userAgent: topUserAgents[Random().nextInt(topUserAgents.length)],
    );
  }
}
