import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/mobile/native_ui/ios_native_settings.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/components/omi_settings.dart';

void main() {
  test('settings projection keeps values, destructive actions and mutation ownership', () async {
    bool? changed;
    var deleted = false;
    final sections = nativeSettingsSections([
      OmiSettingsGroup(header: 'Privacy', footer: 'Description', children: [
        OmiSettingsRow.toggle(title: 'Enabled', value: true, onChanged: (value) => changed = value),
        OmiSettingsRow(title: 'Delete', value: 'Account', isDestructive: true, onTap: () => deleted = true),
      ]),
    ])!;
    expect(sections.single.title, 'Privacy');
    expect(sections.single.footer, 'Description');
    final toggle = sections.single.rows.first;
    expect(toggle.projection['value'], true);
    expect(toggle.accepts('false'), false);
    await toggle.action!(false);
    expect(changed, false);
    final deletion = sections.single.rows.last;
    expect(deletion.projection['destructive'], true);
    expect(deletion.subtitle, 'Account');
    await deletion.action!(null);
    expect(deleted, true);
  });

  test('unsupported controls retain the entire original page', () {
    expect(
        nativeSettingsSections([
          const OmiSettingsGroup(children: [TextField()])
        ]),
        isNull);
    expect(
        nativeSettingsSections([
          const OmiSettingsGroup(children: [OmiSettingsRow(title: 'Progress', trailing: CircularProgressIndicator())])
        ]),
        isNull);
  });

  test('commands reject unexpected payloads and choices', () {
    const action = NativeRow('delete', 'Delete');
    expect(action.accepts(null), true);
    expect(action.accepts('another-id'), false);
    const choice = NativeRow('appearance', 'Appearance',
        kind: 'choice', value: 'system', options: {'system': 'System', 'light': 'Light'});
    expect(choice.accepts('dark'), false);
    expect(choice.accepts('system'), true);
    const text = NativeRow('draft', 'Draft', kind: 'text', value: '');
    expect(text.accepts(List.filled(10001, 'x').join()), false);
    expect(text.accepts(true), false);
  });
  test('nested settings groups keep unique identities', () {
    final groups = nativeSettingsSections([
      Column(children: [
        OmiSettingsGroup(children: [OmiSettingsRow(title: 'First', onTap: () {})])
      ]),
      Column(children: [
        OmiSettingsGroup(children: [OmiSettingsRow(title: 'Second', onTap: () {})])
      ]),
    ])!;
    expect(groups.map((group) => group.id).toSet().length, 2);
    expect(groups.expand((group) => group.rows).map((row) => row.id).toSet().length, 2);
  });

  test('native text preserves the original grapheme limit', () {
    const row = NativeRow('draft', 'Draft', kind: 'text', value: '👨‍👩‍👧‍👦', maximumLength: 2);
    expect(row.valid, true);
    expect(row.accepts('👨‍👩‍👧‍👦a'), true);
    expect(row.accepts('👨‍👩‍👧‍👦ab'), false);
    expect(row.projection['maximumLength'], 2);
    expect(const NativeRow('draft', 'Draft', kind: 'text', value: 'abc', maximumLength: 2).valid, false);
    expect(const NativeRow('draft', 'Draft', kind: 'text', value: '', maximumLength: 0).valid, false);
  });

  test('invalid legacy picker values use the original renderer', () {
    const row = NativeRow('mode', 'Mode', kind: 'choice', value: 'legacy', options: {'system': 'System'});
    expect(row.valid, false);
    expect(const NativeRow('_refresh', 'Reserved').valid, false);
    expect(const NativeRow('toggle', 'Typed', kind: 'toggle', value: 'false').valid, false);
  });
  test('native bridge rejects stale sessions and arbitrary mutation payloads', () async {
    var active = true;
    var writes = 0;
    final rows = [
      NativeRow('enabled', 'Enabled', kind: 'toggle', value: false, action: (_) => writes++),
      NativeRow('disabled', 'Disabled', enabled: false, action: (_) => writes++)
    ];
    Future<void> dispatch(String id, [Object? value]) =>
        dispatchNativeAction(MethodCall('action', {'id': id, 'value': value}), isActive: () => active, rows: rows);
    await dispatch('enabled', true);
    expect(writes, 1);
    for (final command in [() => dispatch('enabled', 'true'), () => dispatch('disabled'), () => dispatch('unknown')]) {
      await expectLater(command(), throwsA(isA<PlatformException>()));
    }
    active = false;
    await expectLater(dispatch('enabled', false), throwsA(isA<PlatformException>()));
    expect(writes, 1);
  });
}
