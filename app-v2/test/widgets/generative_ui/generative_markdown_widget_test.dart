import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/widgets/generative_ui/generative_markdown_widget.dart';
import 'package:nooto_v2/widgets/generative_ui/widgets/rich_list_widget.dart';
import 'package:nooto_v2/widgets/generative_ui/widgets/bar_chart_widget.dart';

Widget _harness(Widget child) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

void main() {
  testWidgets('renders plain markdown when no tags present', (tester) async {
    await tester.pumpWidget(_harness(const GenerativeMarkdownWidget(content: '# Heading\n\nBody text.')));
    expect(find.text('Heading'), findsOneWidget);
    expect(find.byType(RichListWidget), findsNothing);
  });

  testWidgets('renders rich-list widget when tag present', (tester) async {
    const content = '''
<rich-list>
  <item title="Apple" description="A fruit"/>
  <item title="Banana" description="Yellow"/>
</rich-list>
''';
    await tester.pumpWidget(_harness(const GenerativeMarkdownWidget(content: content)));
    await tester.pump();
    expect(find.byType(RichListWidget), findsOneWidget);
    expect(find.text('Apple'), findsOneWidget);
    expect(find.text('Banana'), findsOneWidget);
  });

  testWidgets('renders mixed content (markdown + tag + markdown)', (tester) async {
    const content = '## Top heading\n\n<rich-list><item title="X" description="d"/></rich-list>\n\nSome footer text.';
    await tester.pumpWidget(_harness(const GenerativeMarkdownWidget(content: content)));
    await tester.pump();
    expect(find.byType(RichListWidget), findsOneWidget);
    expect(find.text('Top heading'), findsOneWidget);
    expect(find.text('Some footer text.'), findsOneWidget);
  });

  testWidgets('renders bar chart for chart segment with type=bar', (tester) async {
    const content = '<pie-chart type="bar" title="X"><segment label="A" value="1"/></pie-chart>';
    await tester.pumpWidget(_harness(const GenerativeMarkdownWidget(content: content)));
    await tester.pump();
    expect(find.byType(GenerativeBarChartWidget), findsOneWidget);
  });
}
