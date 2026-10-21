// Active checks of the executable template's Flutter assumptions.
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import '../support/addressability_widgets.dart';

void main() {
  testWidgets('IndexedStack finders distinguish hidden from removed and preserve state', (tester) async {
    final counterKey = GlobalKey<_CounterState>();
    Widget shell(int index) => MaterialApp(
          home: IndexedStack(index: index, children: [
            SizedBox(key: const ValueKey('home'), child: _Counter(key: counterKey)),
            const SizedBox(key: ValueKey('conversations')),
          ]),
        );
    await tester.pumpWidget(shell(0));
    counterKey.currentState!.count = 7;
    final state = counterKey.currentState;
    await tester.pumpWidget(shell(1));
    expect(find.byKey(const ValueKey('home'), skipOffstage: true), findsNothing);
    expect(find.byKey(const ValueKey('home'), skipOffstage: false), findsOneWidget);
    expect(counterKey.currentState, same(state));
    await tester.pumpWidget(shell(0));
    expect(find.byKey(const ValueKey('home')), findsOneWidget);
    expect(counterKey.currentState!.count, 7);
  });

  test('shared constructor predicate includes gestures, Ink and Cupertino controls', () {
    for (final widget in <Widget>[
      GestureDetector(onTap: () {}),
      InkWell(onTap: () {}),
      InkResponse(onLongPress: () {}),
      CupertinoButton(onPressed: () {}, child: const Text('Button')),
      DropdownButton<String>(items: const [], onChanged: (_) {}),
      PopupMenuButton<String>(itemBuilder: (_) => []),
      ListTile(onLongPress: () {}),
      TextFormField(),
      Checkbox(value: false, onChanged: (_) {}),
    ]) {
      expect(isCatalogInteractive(widget), isTrue, reason: '${widget.runtimeType}');
    }
    expect(isCatalogInteractive(const ListTile()), isFalse);
    expect(isCatalogInteractive(const InkWell(), includeDisabled: true), isTrue);
    expect(isCatalogInteractive(const SizedBox()), isFalse);
  });
}

class _Counter extends StatefulWidget {
  const _Counter({super.key});
  @override
  State<_Counter> createState() => _CounterState();
}

class _CounterState extends State<_Counter> {
  int count = 0;
  @override
  Widget build(BuildContext context) => Text('$count');
}
