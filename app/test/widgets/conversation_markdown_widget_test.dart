import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';

void main() {
  testWidgets('conversation markdown is lazy inside a sliver viewport', (tester) async {
    final content = List.generate(200, (index) => 'Block $index').join('\n\n');

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: CustomScrollView(slivers: [ConversationMarkdownSliver(content: content)]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(SingleChildScrollView), findsNothing);
    expect(find.text('Block 199'), findsNothing);

    await tester.fling(find.byType(CustomScrollView), const Offset(0, -100000), 10000);
    await tester.pumpAndSettle();

    expect(find.text('Block 199'), findsOneWidget);
  });

  testWidgets('conversation markdown preserves common block structures', (tester) async {
    const content = '''# Heading

- first item
- second item

> quoted text

```dart
final answer = 42;
```
''';

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: const Scaffold(
          body: CustomScrollView(slivers: [ConversationMarkdownSliver(content: content)]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Heading'), findsOneWidget);
    expect(find.text('first item'), findsOneWidget);
    expect(find.text('second item'), findsOneWidget);
    expect(find.text('quoted text'), findsOneWidget);
    expect(find.text('final answer = 42;'), findsOneWidget);
  });
}
