import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/settings_destinations.dart';

void main() {
  test('help center opens in the app language when it has one', () {
    expect(helpCenterUrl(const Locale('de')).toString(), 'https://help.omi.me/de/');
    expect(helpCenterUrl(const Locale('zh')).toString(), 'https://help.omi.me/zh-CN/');
    expect(helpCenterUrl(const Locale('no')).toString(), 'https://help.omi.me/nb/');
  });

  test('languages the help center lacks fall back to English', () {
    expect(helpCenterUrl(const Locale('kn')).toString(), 'https://help.omi.me/en/');
    expect(helpCenterUrl(const Locale('en', 'US')).toString(), 'https://help.omi.me/en/');
  });
}
