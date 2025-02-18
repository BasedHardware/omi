import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

// A simple widget to test
class MyWidget extends StatelessWidget {
  final String text;
  MyWidget({required this.text});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Center(
          child: Text(text),
        ),
      ),
    );
  }
}

void main() {
  testWidgets('MyWidget has a text "Hello, World!"', (WidgetTester tester) async {
    // Build the widget
    await tester.pumpWidget(MyWidget(text: 'Hello, World!'));

    // Verify the text is found
    expect(find.text('Hello, World!'), findsOneWidget);
  });
}
