import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/native_plan_projection.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';

void main() {
  test('native plan selection preserves backend price copy, entitlements and exact callbacks', () async {
    final l10n = await AppLocalizations.delegate.load(const Locale('ja'));
    var selected = 0;
    bool? yearly;
    final rows = nativePlanRows(
        l10n,
        Column(children: [
          PlanBillingPeriodToggle(isYearly: true, savePercent: 12, onChanged: (value) => yearly = value),
          Padding(
              padding: EdgeInsets.zero,
              child: PlanOptionCard(
                  key: const ValueKey('price_from_backend_year'),
                  isSelected: true,
                  title: 'Backend tier title',
                  subtitle: 'Backend annual disclosure',
                  price: 'JPY 1200 / year',
                  onTap: () => selected++,
                  isActive: true,
                  endsOnDate: '2030-01-01',
                  saveTag: 'Backend savings',
                  features: const ['Backend allowance'],
                  desktopAccess: false)),
        ]),
        enabled: true)!;
    expect(rows.every((row) => row.valid), true);
    expect(rows.last.subtitle, contains('JPY 1200 / year'));
    expect(rows.last.subtitle, contains('Backend annual disclosure'));
    expect(rows.last.subtitle, contains('Backend allowance'));
    expect(rows.last.subtitle, contains(l10n.noDesktopAccess));
    expect(rows.last.subtitle, contains(l10n.endsOnDate('2030-01-01')));
    expect(rows.first.options['year'], contains(l10n.savePercent(12)));
    await rows.first.action!('month');
    await rows.last.action!(null);
    expect(yearly, false);
    expect(selected, 1);
    expect(rows.last.id, 'plan_price_from_backend_year');
  });
  test('unknown or duplicate plan controls retain the complete existing renderer', () async {
    final l10n = await AppLocalizations.delegate.load(const Locale('en'));
    expect(nativePlanRows(l10n, const TextField(), enabled: true), isNull);
    final card = PlanOptionCard(
        key: const ValueKey('same'),
        isSelected: false,
        title: 'Tier',
        subtitle: null,
        price: 'Existing price',
        onTap: () {});
    expect(nativePlanRows(l10n, Column(children: [card, card]), enabled: true), isNull);
    expect(nativePlanRows(l10n, card, enabled: false)!.single.projection['enabled'], false);
  });
}
