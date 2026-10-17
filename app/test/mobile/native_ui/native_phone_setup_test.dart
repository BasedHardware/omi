import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/phone_calls/phone_setup_number_page.dart';
import 'package:omi/providers/phone_call_provider.dart';

class _PhoneOwner extends PhoneCallProvider {
  _PhoneOwner() : super.forTesting();
  final verified = <String>[];
  @override
  Future<bool> startVerification(String phoneNumber) async {
    verified.add(phoneNumber);
    return false;
  }
}

void main() {
  Future<_PhoneOwner> host(WidgetTester tester) async {
    final owner = _PhoneOwner();
    addTearDown(owner.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<PhoneCallProvider>.value(
      value: owner,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: PhoneSetupNumberPage(),
      ),
    ));
    await tester.pump();
    return owner;
  }

  NativeRow row(WidgetTester tester, String id) => tester
      .widget<IosNativeSurface>(find.byType(IosNativeSurface))
      .sections
      .expand((section) => section.rows)
      .firstWhere((row) => row.id == id);

  testWidgets('country and number edits keep libphonenumber validation without starting verification', (tester) async {
    final owner = await host(tester);
    expect(row(tester, 'phone_number_input').keyboard, 'phone');
    expect(row(tester, 'phone_number_country').optionSearch, isNotEmpty);
    expect(row(tester, 'phone_number_country').optionClose, isNotEmpty);
    expect(row(tester, 'phone_number_continue').enabled, false);
    await row(tester, 'phone_number_country').action!('EE');
    await row(tester, 'phone_number_input').action!('5142537');
    await tester.pump();
    expect(row(tester, 'phone_number_country').value, 'EE');
    expect(row(tester, 'phone_number_continue').enabled, true);
    expect(owner.verified, isEmpty);
    await row(tester, 'phone_number_input').action!('123');
    await tester.pump();
    expect(row(tester, 'phone_number_continue').enabled, false);
    expect(owner.verified, isEmpty);
  });

  testWidgets('explicit Continue uses the original owner and preserves an international prefix', (tester) async {
    final owner = await host(tester);
    await row(tester, 'phone_number_input').action!('+3725142537');
    await tester.pump();
    expect(row(tester, 'phone_number_continue').enabled, true);
    await row(tester, 'phone_number_continue').action!(null);
    await tester.pump();
    expect(owner.verified, ['+3725142537']);
    expect(row(tester, 'phone_number_error').title, isNotEmpty);
  });

  test('keyboard metadata cannot turn another control into input or request an unknown keyboard', () {
    expect(const NativeRow('number', 'Number', kind: 'text', value: '', keyboard: 'phone').valid, true);
    expect(const NativeRow('number', 'Number', kind: 'text', value: '', keyboard: 'unknown').valid, false);
    expect(const NativeRow('delete', 'Delete', keyboard: 'phone').valid, false);
  });

  test('searchable choices require localized search and close labels on a choice control', () {
    expect(
        const NativeRow('country', 'Country',
                kind: 'choice',
                value: 'US',
                options: {'US': 'United States'},
                optionSearch: 'Search countries',
                optionClose: 'Close')
            .valid,
        true);
    expect(
        const NativeRow('country', 'Country',
                kind: 'choice', value: 'US', options: {'US': 'United States'}, optionSearch: 'Search countries')
            .valid,
        false);
    expect(const NativeRow('button', 'Button', optionSearch: 'Search', optionClose: 'Close').valid, false);
  });
}
