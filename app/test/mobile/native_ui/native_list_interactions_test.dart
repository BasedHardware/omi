import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import '../../../integration_test/support/native_host_harness.dart';
import 'native_test_host.dart';

const _fallback = 'complete flutter surface';

NativeRow _conversation(String id, {List<Object?>? sink}) =>
    NativeRow(id, 'Conversation $id', kind: 'navigation', options: const {'delete': 'Delete'}, action: sink?.add);

List<NativeSection> _library({List<Object?>? sink}) => [
      NativeSection('today', [
        _conversation('a', sink: sink),
        _conversation('b', sink: sink),
        _conversation('c', sink: sink),
        NativeRow('more', 'Show more', action: sink?.add),
      ]),
    ];

Future<void> _dispatch(String id, Object? value,
        {NativeSelection? selection, List<NativeSection> sections = const []}) =>
    dispatchNativeAction(MethodCall('action', {'id': id, 'value': value}),
        isActive: () => true,
        rows: sections.expand((section) => section.rows),
        selection: selection,
        sections: sections);

Matcher get _refused =>
    throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'invalid_native_action'));

/// Pumps [surface] on the hermetic host; true when it rendered natively rather than [_fallback].
Future<bool> _rendersNatively(WidgetTester tester, Widget surface) async {
  await tester.pumpWidget(NativeTestHost.app(surface));
  await NativeTestHost.settle(tester);
  final native = find.byType(UiKitView).evaluate().isNotEmpty;
  expect(native, find.text(_fallback).evaluate().isEmpty, reason: 'Exactly one presentation renders');
  return native;
}

Future<Object?> _sendFromNative(NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  return const StandardMethodCodec().decodeEnvelope(reply!);
}

void main() {
  group('NativeSelection', () {
    final sections = _library();

    test('is valid only for selectable section rows and a selected subset of them', () {
      final selection = NativeSelection(selected: const {'b'}, selectable: const {'c', 'a', 'b'}, action: (_) {});
      expect(selection.validFor(sections), true);
      expect(selection.projection, {
        'selected': ['b'],
        'selectable': ['a', 'b', 'c'],
      });
      expect(NativeSelection(selected: const {}, selectable: const {'a', 'foreign'}, action: (_) {}).validFor(sections),
          false,
          reason: 'selectable must be section rows');
      expect(
          NativeSelection(selected: const {'more'}, selectable: const {'a'}, action: (_) {}).validFor(sections), false,
          reason: 'selected must be selectable');
      final many = [for (var index = 0; index <= 10000; index++) NativeRow('row_$index', 'Row', kind: 'label')];
      final ids = many.map((row) => row.id).toSet();
      expect(
          NativeSelection(selected: const {}, selectable: ids, action: (_) {}).validFor([NativeSection('all', many)]),
          false,
          reason: 'at most 10000 selectable ids');
      expect(
          NativeSelection(selected: const {}, selectable: ids.skip(1).toSet(), action: (_) {})
              .validFor([NativeSection('all', many)]),
          true);
    });

    test("'_selection' passes the desired ids through and refuses anything else", () async {
      final received = <Object?>[];
      final selection = NativeSelection(selected: const {'a'}, selectable: const {'a', 'b', 'c'}, action: received.add);
      await _dispatch('_selection', ['c', 'a'], selection: selection, sections: sections);
      await _dispatch('_selection', <Object?>[], selection: selection, sections: sections);
      expect(received, [
        ['c', 'a'],
        <String>[],
      ]);
      expect(received.first, isA<List<String>>());
      for (final value in <Object?>[
        null,
        'a',
        {'a': true},
        [1],
        ['a', null],
        ['a', 'a'],
        ['a', 'unknown'],
        ['more'],
      ]) {
        await expectLater(_dispatch('_selection', value, selection: selection, sections: sections), _refused,
            reason: '$value');
      }
      await expectLater(_dispatch('_selection', ['a'], sections: sections), _refused,
          reason: 'A surface without a selection has no selection command');
      final oversized = [for (var index = 0; index <= 10000; index++) 'row_$index'];
      final large = NativeSelection(selected: const {}, selectable: oversized.toSet(), action: received.add);
      await expectLater(_dispatch('_selection', oversized, selection: large), _refused);
      expect(received, hasLength(2));
    });
  });

  group('reorder', () {
    test("'_reorder' accepts only an exact permutation of the section's current rows", () async {
      final orders = <Object?>[];
      NativeSection tasks(List<String> ids) =>
          NativeSection('tasks', [for (final id in ids) NativeRow(id, id, kind: 'task', value: false, action: (_) {})],
              reorder: orders.add);
      final current = tasks(['a', 'b', 'c']);
      final other = NativeSection('later', [NativeRow('d', 'd', kind: 'task', value: false, action: (_) {})],
          reorder: orders.add);
      final sections = [current, other];
      await _dispatch('_reorder:tasks', ['c', 'a', 'b'], sections: sections);
      expect(orders, [
        ['c', 'a', 'b']
      ]);
      expect(orders.single, isA<List<String>>());
      for (final value in <Object?>[
        ['a', 'a', 'b'], // duplicate
        ['a', 'b'], // missing
        ['a', 'b', 'c', 'e'], // extra
        ['a', 'b', 'd'], // another section's row
        'a,b,c',
        null,
        ['a', 'b', 3],
      ]) {
        await expectLater(_dispatch('_reorder:tasks', value, sections: sections), _refused, reason: '$value');
      }
      // A permutation of rows the owner has since replaced is stale.
      await expectLater(
          _dispatch('_reorder:tasks', [
            'b',
            'a',
            'c'
          ], sections: [
            tasks(['a', 'b', 'x']),
            other
          ]),
          _refused);
      await expectLater(_dispatch('_reorder:missing', <String>[], sections: sections), _refused);
      await expectLater(
          _dispatch('_reorder:plain', [
            'a'
          ], sections: const [
            NativeSection('plain', [NativeRow('a', 'a', kind: 'label')])
          ]),
          _refused,
          reason: 'A section without reorder has no reorder command');
      expect(orders, hasLength(1));
    });

    test('a reorderable section holds only list rows', () {
      for (final kind in ['task', 'navigation', 'label', 'toggle', 'menu']) {
        final row = NativeRow('row', 'Row', kind: kind, value: ['task', 'toggle'].contains(kind) ? false : null);
        expect(NativeSection('s', [row], reorder: (_) {}).valid, true, reason: kind);
      }
      expect(NativeSection('s', const [NativeRow('row', 'Row')], reorder: (_) {}).valid, false);
      expect(
          NativeSection('s', const [NativeRow('row', 'Row', kind: 'text', value: '')], reorder: (_) {}).valid, false);
      expect(const NativeSection('s', [NativeRow('row', 'Row')]).projection['reorderable'], false);
      expect(NativeSection('s', const [], reorder: (_) {}).projection['reorderable'], true);
    });
  });

  test('collapsible sections need a title', () {
    expect(const NativeSection('overdue', [], collapsible: true).valid, false);
    const titled = NativeSection('overdue', [], title: 'Overdue', collapsible: true);
    expect(titled.valid, true);
    expect(titled.projection['collapsible'], true);
  });

  test('indent is 0..3 on list rows only', () {
    for (final kind in ['task', 'navigation', 'label', 'toggle', 'menu']) {
      final value = ['task', 'toggle'].contains(kind) ? false : null;
      for (final indent in [0, 3]) {
        expect(NativeRow('row', 'Row', kind: kind, value: value, indent: indent).valid, true, reason: '$kind $indent');
      }
      for (final indent in [-1, 4]) {
        expect(NativeRow('row', 'Row', kind: kind, value: value, indent: indent).valid, false, reason: '$kind $indent');
      }
    }
    expect(const NativeRow('row', 'Row', indent: 1).valid, false);
    expect(const NativeRow('row', 'Row', kind: 'text', value: '', indent: 1).valid, false);
    expect(const NativeRow('row', 'Row', kind: 'label', indent: 2).projection['indent'], 2);
    expect(const NativeRow('row', 'Row').projection['indent'], isNull);
  });

  test('swipe ids are row options, on one edge, at most three per edge, on task, navigation and menu rows', () async {
    const options = {'complete': 'Complete', 'pin': 'Pin', 'star': 'Star', 'open': 'Open', 'delete': 'Delete'};
    NativeRow row({String kind = 'navigation', List<String> leading = const [], List<String> trailing = const []}) =>
        NativeRow('row', 'Row',
            kind: kind,
            value: kind == 'task' ? false : null,
            options: options,
            swipeLeading: leading,
            swipeTrailing: trailing);
    expect(row(leading: ['complete'], trailing: ['delete']).valid, true);
    expect(row(kind: 'task', leading: ['complete', 'pin', 'star'], trailing: ['delete', 'open']).valid, true);
    expect(row(kind: 'menu', trailing: ['delete']).valid, true);
    expect(row(trailing: ['archive']).valid, false, reason: 'not an option');
    expect(row(leading: ['delete'], trailing: ['delete']).valid, false, reason: 'on both edges');
    expect(row(leading: ['complete', 'pin', 'star', 'open']).valid, false, reason: 'more than three');
    expect(row(trailing: ['delete', 'delete']).valid, false, reason: 'repeated');
    expect(row(kind: 'label', trailing: ['delete']).valid, false);
    expect(row(kind: 'button', trailing: ['delete']).valid, false);
    final swiped = row(leading: ['complete'], trailing: ['delete']);
    expect(swiped.projection['swipeLeading'], ['complete']);
    expect(swiped.projection['swipeTrailing'], ['delete']);

    // A swipe sends the option id like the context menu does.
    final chosen = <Object?>[];
    final person = NativeRow('person', 'Avery',
        kind: 'navigation', options: const {'pin': 'Pin'}, swipeTrailing: const ['pin'], action: chosen.add);
    await dispatchNativeAction(const MethodCall('action', {'id': 'person', 'value': 'pin'}),
        isActive: () => true, rows: [person]);
    expect(chosen, ['pin']);
  });

  group('surface', () {
    testWidgets('projects the selection, bottom bar, section flags and expand/collapse copy', (tester) async {
      final host = NativeTestHost.install();
      final selections = <Object?>[];
      final deleted = <Object?>[];
      final orders = <Object?>[];
      expect(
          await _rendersNatively(
              tester,
              IosNativeSurface(
                  title: 'Conversations',
                  fallback: const Text(_fallback),
                  sections: [
                    ..._library(),
                    const NativeSection('overdue', [NativeRow('late', 'Late', kind: 'label', indent: 1)],
                        title: 'Overdue', collapsible: true),
                  ],
                  selection:
                      NativeSelection(selected: const {'b'}, selectable: const {'a', 'b'}, action: selections.add),
                  bottomBar: [
                    const NativeRow('count', '1 selected', kind: 'label'),
                    NativeRow('bulk_delete', 'Delete', symbol: 'trash', destructive: true, action: deleted.add),
                  ])),
          true);
      final snapshot = tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;
      final l10n = lookupAppLocalizations(const Locale('en'));
      expect(snapshot['expandLabel'], l10n.expand);
      expect(snapshot['collapseLabel'], l10n.collapseAction);
      expect(snapshot['selection'], {
        'selected': ['b'],
        'selectable': ['a', 'b'],
      });
      expect((snapshot['bottomBar'] as List).map((row) => (row as Map)['id']), ['count', 'bulk_delete']);
      final overdue = (snapshot['sections'] as List).last as Map;
      expect(overdue['collapsible'], true);
      expect(overdue['reorderable'], false);
      expect(((overdue['rows'] as List).single as Map)['indent'], 1);
      expect(nativeProjectedRow(tester, 'bulk_delete').title, 'Delete', reason: 'Host tests find bottom-bar rows');

      // Commands reach the owner through the surface: the desired set, and bottom-bar rows like toolbar rows.
      expect(await _sendFromNative(host, '_selection', ['a', 'b']), isNull);
      expect(selections, [
        ['a', 'b']
      ]);
      expect(await _sendFromNative(host, 'bulk_delete'), isNull);
      expect(deleted, [null]);
      await expectLater(_sendFromNative(host, '_selection', ['c']), _refused, reason: 'c is not selectable');
      await expectLater(_sendFromNative(host, '_reorder:today', ['c', 'b', 'a', 'more']), _refused,
          reason: 'today is not reorderable');

      await tester.pumpWidget(NativeTestHost.app(
          IosNativeSurface(key: UniqueKey(), title: 'Tasks', fallback: const Text(_fallback), sections: [
        NativeSection(
            'tasks',
            [
              for (final id in ['x', 'y']) NativeRow(id, id, kind: 'task', value: false, action: (_) {})
            ],
            reorder: orders.add),
      ])));
      await NativeTestHost.settle(tester);
      expect(await _sendFromNative(host, '_reorder:tasks', ['y', 'x']), isNull);
      expect(orders, [
        ['y', 'x']
      ]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('bottom bar limits, list mode and selection conflicts restore the complete Flutter surface',
        (tester) async {
      NativeTestHost.install();
      NativeRow button(String id) => NativeRow(id, id, action: (_) {});
      Widget surface({
        List<NativeRow> bottomBar = const [],
        List<NativeRow> toolbar = const [],
        NativeSelection? selection,
        NativeChat? chat,
        NativeReader? reader,
        NativeAction? reorder,
        bool collapsible = false,
      }) =>
          IosNativeSurface(
              key: UniqueKey(),
              title: 'Library',
              fallback: const Text(_fallback),
              toolbar: toolbar,
              chat: chat,
              reader: reader,
              selection: selection,
              bottomBar: bottomBar,
              sections: [
                NativeSection('today', const [NativeRow('a', 'A', kind: 'label'), NativeRow('b', 'B', kind: 'label')],
                    reorder: reorder, collapsible: collapsible),
              ]);
      const label = NativeRow('count', '2 selected', kind: 'label');
      final six = [label, for (var index = 0; index < 5; index++) button('action_$index')];
      expect(await _rendersNatively(tester, surface(bottomBar: six)), true);
      expect(
          await _rendersNatively(
              tester,
              surface(bottomBar: [
                const NativeRow('menu', 'More', kind: 'menu', options: {'move': 'Move'})
              ])),
          true);
      expect(await _rendersNatively(tester, surface(bottomBar: [...six, button('action_5')])), false,
          reason: 'at most six');
      expect(
          await _rendersNatively(tester, surface(bottomBar: [label, const NativeRow('other', 'Other', kind: 'label')])),
          false,
          reason: 'one label');
      expect(
          await _rendersNatively(tester,
              surface(bottomBar: [NativeRow('switch', 'Switch', kind: 'toggle', value: false, action: (_) {})])),
          false,
          reason: 'labels, buttons and menus only');
      expect(await _rendersNatively(tester, surface(bottomBar: [button('a')])), false,
          reason: 'unique across sections');
      expect(await _rendersNatively(tester, surface(bottomBar: [button('save')], toolbar: [button('save')])), false,
          reason: 'unique across the toolbar');
      const chat = NativeChat(draft: '', placeholder: 'Ask', actions: []);
      expect(await _rendersNatively(tester, surface(bottomBar: [button('send')], chat: chat)), false);
      expect(await _rendersNatively(tester, surface(bottomBar: [button('play')], reader: const NativeReader())), false);
      expect(
          await _rendersNatively(
              tester,
              surface(
                  bottomBar: [button('chat_send')],
                  chat: NativeChat(draft: '', placeholder: 'Ask', actions: [button('chat_send')]))),
          false,
          reason: 'unique across chat actions');
      NativeRow navigation() => NativeRow('main_destination', '',
          kind: 'segmented',
          value: 'home',
          options: const {
            'home': 'Home',
            'tasks': 'Tasks',
            'memories': 'Memories',
            'apps': 'Apps',
            'settings': 'Settings'
          },
          action: (_) {});
      Widget shell({List<NativeRow> bottomBar = const []}) => IosNativeSurface(
          key: UniqueKey(),
          title: '',
          sections: const [],
          navigation: navigation(),
          bottomBar: bottomBar,
          fallback: const Text(_fallback));
      expect(await _rendersNatively(tester, shell()), true);
      expect(await _rendersNatively(tester, shell(bottomBar: [button('library_delete')])), false,
          reason: 'not with the tab bar');

      final selection = NativeSelection(selected: const {'a'}, selectable: const {'a', 'b'}, action: (_) {});
      expect(await _rendersNatively(tester, surface(selection: selection)), true);
      expect(await _rendersNatively(tester, surface(selection: selection, reorder: (_) {})), false,
          reason: 'selection and reorder are mutually exclusive');
      expect(await _rendersNatively(tester, surface(reorder: (_) {})), true);
      expect(await _rendersNatively(tester, surface(selection: selection, chat: chat)), false);
      expect(await _rendersNatively(tester, surface(reorder: (_) {}, reader: const NativeReader())), false);
      expect(
          await _rendersNatively(
              tester, surface(selection: NativeSelection(selected: const {}, selectable: const {'z'}, action: (_) {}))),
          false);
      expect(await _rendersNatively(tester, surface(collapsible: true)), false, reason: 'an untitled collapsible');
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('a native modal never carries list interactions', (tester) async {
    NativeTestHost.install();
    const config = MethodChannel('com.omi.native_ui/config');
    final presented = <MethodCall>[];
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(config, (call) async {
      presented.add(call);
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(config, null));
    await tester.pumpWidget(NativeTestHost.app(const SizedBox()));
    final context = tester.element(find.byType(SizedBox));
    const actions = [NativeRow('cancel', 'Cancel'), NativeRow('save', 'Save')];
    for (final sections in [
      [
        const NativeSection('fields', [NativeRow('note', 'Note', kind: 'label', indent: 1)])
      ],
      [
        const NativeSection('fields', [
          NativeRow('person', 'Avery', kind: 'navigation', options: {'pin': 'Pin'}, swipeTrailing: ['pin'])
        ])
      ],
      [
        const NativeSection('fields', [NativeRow('note', 'Note', kind: 'label')], title: 'Notes', collapsible: true)
      ],
      [
        NativeSection('fields', const [NativeRow('note', 'Note', kind: 'label')], reorder: (_) {})
      ],
    ]) {
      expect(await showIosNativeModal(context, title: 'Edit', actions: actions, sections: sections), isNull);
    }
    expect(presented.where((call) => call.method == 'present'), isEmpty);
  });
}
