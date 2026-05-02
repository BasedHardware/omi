import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/services/app_links_service.dart';

void main() {
  group('AppLinksService.parseLink', () {
    test('parses app-setup-complete with app_id and explicit status', () {
      final link = AppLinksService.parseLink(
        Uri.parse('nooto://app-setup-complete?app_id=nooto-jira&status=success'),
      );

      expect(link, isA<AppSetupComplete>());
      final setup = link as AppSetupComplete;
      expect(setup.appId, 'nooto-jira');
      expect(setup.status, 'success');
    });

    test('defaults status to "success" when only app_id is provided', () {
      final link = AppLinksService.parseLink(
        Uri.parse('nooto://app-setup-complete?app_id=nooto-jira'),
      );

      expect(link, isA<AppSetupComplete>());
      final setup = link as AppSetupComplete;
      expect(setup.appId, 'nooto-jira');
      expect(setup.status, 'success');
    });

    test('returns UnknownDeepLink when app_id is missing', () {
      final link = AppLinksService.parseLink(
        Uri.parse('nooto://app-setup-complete?status=success'),
      );

      expect(link, isA<UnknownDeepLink>());
    });

    test('returns UnknownDeepLink for unrecognized paths', () {
      final link = AppLinksService.parseLink(
        Uri.parse('nooto://other-path'),
      );

      expect(link, isA<UnknownDeepLink>());
    });
  });
}
