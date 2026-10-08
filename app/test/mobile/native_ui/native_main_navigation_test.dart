import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_main_navigation.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('root navigation mounts pages lazily, preserves state and honors explicit Home navigation',
      (tester) async {
    var homeIndex = 0, revision = 0;
    late StateSetter update;
    final mounts = <String, int>{};
    final selected = <int>[];
    var homeReselections = 0;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: StatefulBuilder(builder: (context, setState) {
        update = setState;
        return IosNativeMainShell(
          homeIndex: homeIndex,
          navigationRevision: revision,
          onHomeTabSelected: (index) => selected.add(index),
          onHomeReselected: () => homeReselections++,
          pages: {
            for (final id in nativeMainDestinations)
              id: (_) => _Page(id, onMount: () => mounts.update(id, (value) => value + 1, ifAbsent: () => 1)),
          },
        );
      })),
    ));
    await tester.pumpAndSettle();
    expect(mounts, {'home': 1});
    Future<void> select(String id) async {
      final bar = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      await dispatchNativeAction(MethodCall('action', {'id': 'main_destination', 'value': id}),
          isActive: () => true, rows: [bar.navigation!]);
      await tester.pumpAndSettle();
    }

    await select('memories');
    await tester.tap(find.byKey(const Key('count_memories')));
    await tester.pump();
    await select('tasks');
    await select('apps');
    await select('settings');
    await select('memories');
    expect(find.text('memories:1'), findsOneWidget);
    expect(mounts.values, everyElement(1));
    expect(selected, [1]);
    update(() {
      homeIndex = 0;
      revision++;
    });
    await tester.pumpAndSettle();
    expect(find.text('home:0'), findsOneWidget);
    await select('home');
    expect(homeReselections, 1);
    final pageRect = tester.getRect(find.byKey(const Key('native_main_pages')));
    final barRect = tester.getRect(find.byKey(const Key('native_main_navigation')));
    expect(pageRect.bottom, lessThanOrEqualTo(barRect.top));
    final navigation = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).navigation!;
    await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': 'main_destination', 'value': '/arbitrary'}),
            isActive: () => true, rows: [navigation]),
        throwsA(isA<PlatformException>()));
    await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': 'main_destination', 'value': 'tasks'}),
            isActive: () => false, rows: [navigation]),
        throwsA(isA<PlatformException>()));
    expect(find.text('home:0'), findsOneWidget);
  });
}

class _Page extends StatefulWidget {
  const _Page(this.id, {required this.onMount});
  final String id;
  final VoidCallback onMount;
  @override
  State<_Page> createState() => _PageState();
}

class _PageState extends State<_Page> {
  int count = 0;
  @override
  void initState() {
    super.initState();
    widget.onMount();
  }

  @override
  Widget build(BuildContext context) => TextButton(
      key: Key('count_${widget.id}'), onPressed: () => setState(() => count++), child: Text('${widget.id}:$count'));
}
