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

  test('section headers preserve copy and reject unsupported or dangling controls', () {
    final sections = nativeSettingsSections([
      const OmiSectionHeader('Recording', subtitle: 'Your choice', trailing: Text('BETA')),
      OmiSettingsGroup(children: [OmiSettingsRow.toggle(title: 'Offline', value: false, onChanged: (_) {})]),
    ], trailingText: (widget) => widget is Text ? widget.data : null)!;
    expect(sections.single.title, 'Recording');
    expect(sections.single.footer, 'Your choice\nBETA');
    expect(nativeSettingsSections([const OmiSectionHeader('Unrepresented')]), isNull);
    expect(
        nativeSettingsSections([
          const OmiSectionHeader('Recording', trailing: CircularProgressIndicator()),
          const OmiSettingsGroup(children: []),
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
  test('native context menus and palette stay within the current projection', () async {
    final chosen = <Object?>[];
    final person = NativeRow('person_1', 'Avery',
        kind: 'navigation', level: 2, options: const {'pin': 'Pin', 'delete': 'Delete'}, action: chosen.add);
    await dispatchNativeAction(const MethodCall('action', {'id': 'person_1', 'value': 'pin'}),
        isActive: () => true, rows: [person]);
    expect(chosen, ['pin']);
    expect(person.accepts('delete_other_person'), false);
    expect(person.accepts(null), true);
    expect(const NativeRow('person', 'Name', level: 4).valid, false);
    const color = NativeRow('color', 'Color', kind: 'color', value: '#3B82F6', options: {'#3B82F6': 'Color 1'});
    expect(color.valid, true);
    expect(color.accepts('#000000'), false);
    expect(
        const NativeRow('color', 'Color', kind: 'color', value: 'invalid', options: {'invalid': 'Color'}).valid, false);
  });
  test('visibility is opt-in and cannot invoke a mutation', () async {
    var loads = 0;
    var deletes = 0;
    final more = NativeRow('more', 'Show more', onVisible: (_) => loads++);
    final deletion = NativeRow('delete', 'Delete', action: (_) => deletes++);
    expect(more.projection['visibilityEnabled'], true);
    expect(deletion.projection['visibilityEnabled'], false);
    await dispatchNativeAction(const MethodCall('action', {'id': '_visible:more'}),
        isActive: () => true, rows: [more, deletion]);
    expect(loads, 1);
    await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': '_visible:delete'}),
            isActive: () => true, rows: [more, deletion]),
        throwsA(isA<PlatformException>()));
    expect(deletes, 0);
  });
  test('thumbnails allow selected local files and HTTPS assets only', () {
    expect(nativeImageUri('/sandbox/my photo.jpg'), 'file:///sandbox/my%20photo.jpg');
    expect(nativeImageUri('https://assets.example/image.jpg'), 'https://assets.example/image.jpg');
    for (final uri in [
      'javascript:alert(1)',
      'http://example.com/a',
      'file://other-host/a',
      'https://user:password@example.com/a',
      'relative.png'
    ]) {
      expect(nativeImageUri(uri), isNull);
      expect(NativeRow('image', 'Image', imageUri: uri).valid, false);
    }
    expect(nativeImageUri('/${' ' * 4095}'), isNull);
  });
  test('native voice waveform rejects malformed amplitudes', () {
    expect(
        const NativeRow('wave', 'Recording', kind: 'waveform', points: [
          {'x': 0, 'y': .5, 'label': ''}
        ]).valid,
        true);
    for (final y in [double.nan, double.infinity, 2]) {
      expect(
          NativeRow('wave', 'Recording', kind: 'waveform', points: [
            {'x': 0, 'y': y, 'label': ''}
          ]).valid,
          false);
    }
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
