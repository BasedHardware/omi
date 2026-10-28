import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('heavy semantics off leaves the tree disabled', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Text('Synthetic')));
    expect(tester.binding.semanticsEnabled, isFalse);
  }, semanticsEnabled: false);

  testWidgets('accessibility measurement explicitly enables semantics', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Text('Synthetic')));
    expect(tester.binding.semanticsEnabled, isTrue);
    expect(tester.getSemantics(find.text('Synthetic')).label, 'Synthetic');
  }, semanticsEnabled: true);
}
