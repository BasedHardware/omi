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

  testWidgets('conversation markdown headers keep vertical breathing room', (tester) async {
    const content = '''Intro paragraph.

## Iran conflict

Body under h2.

### Strait of Hormuz

Body under h3.

#### Drones and mines

Body under h4.
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

    for (final title in ['Iran conflict', 'Strait of Hormuz', 'Drones and mines']) {
      final padding = tester.widgetList<Padding>(find.ancestor(of: find.text(title), matching: find.byType(Padding)));
      expect(
        padding.any((widget) => widget.padding == conversationMarkdownHeaderPadding),
        isTrue,
        reason: 'expected header padding on "$title"',
      );
    }
  });
}
