import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/widgets/generative_ui/xml_parser.dart';

void main() {
  group('XmlTagParser.containsGenerativeTags', () {
    test('returns false for plain markdown', () {
      const content = '## Heading\n\nJust some **bold** text and a [link](https://x).';
      expect(XmlTagParser.containsGenerativeTags(content), isFalse);
    });

    test('detects rich-list', () {
      const content = '<rich-list><item title="x"/></rich-list>';
      expect(XmlTagParser.containsGenerativeTags(content), isTrue);
    });

    test('detects pie-chart', () {
      const content = '<pie-chart type="donut"><segment label="A" value="10"/></pie-chart>';
      expect(XmlTagParser.containsGenerativeTags(content), isTrue);
    });

    test('detects accordion', () {
      const content = '<accordion><section title="x">y</section></accordion>';
      expect(XmlTagParser.containsGenerativeTags(content), isTrue);
    });
  });

  group('XmlTagParser.parse — plain markdown passthrough', () {
    test('returns single MarkdownSegment when no tags', () {
      final p = XmlTagParser();
      final segs = p.parse('# Title\nContent.');
      expect(segs, hasLength(1));
      expect(segs.single, isA<MarkdownSegment>());
      expect((segs.single as MarkdownSegment).content, '# Title\nContent.');
    });

    test('handles empty content', () {
      final p = XmlTagParser();
      final segs = p.parse('');
      expect(segs, hasLength(1));
      expect(segs.single, isA<MarkdownSegment>());
    });
  });

  group('XmlTagParser.parse — rich-list', () {
    test('parses well-formed rich-list with multiple items', () {
      final p = XmlTagParser();
      const content = '''
<rich-list>
  <item title="One" description="First"/>
  <item title="Two" url="https://x.com"/>
  <item title="Three" thumb="https://x.com/i.png"/>
</rich-list>
''';
      final segs = p.parse(content);
      // Filter out any empty markdown wrappers around the tag.
      final richLists = segs.whereType<RichListSegment>().toList();
      expect(richLists, hasLength(1));
      expect(richLists.single.items, hasLength(3));
      expect(richLists.single.items[0].title, 'One');
      expect(richLists.single.items[0].description, 'First');
      expect(richLists.single.items[1].url, 'https://x.com');
      expect(richLists.single.items[2].thumbnailUrl, 'https://x.com/i.png');
    });
  });

  group('XmlTagParser.parse — chart', () {
    test('parses bar chart with segments', () {
      final p = XmlTagParser();
      const content = '''
<pie-chart type="bar" title="Sales">
  <segment label="A" value="40"/>
  <segment label="B" value="60"/>
</pie-chart>
''';
      final segs = p.parse(content);
      final charts = segs.whereType<PieChartSegment>().toList();
      expect(charts, hasLength(1));
      expect(charts.single.data.title, 'Sales');
      expect(charts.single.data.segments, hasLength(2));
      expect(charts.single.data.segments[0].value, 40);
      expect(charts.single.data.isPieStyle, isFalse);
    });
  });

  group('XmlTagParser.parse — malformed XML', () {
    test('content with unclosed tag falls through to markdown', () {
      final p = XmlTagParser();
      // No closing </rich-list> tag — containsGenerativeTags returns false,
      // and the entire string is preserved as-is in a MarkdownSegment.
      const content = '<rich-list><item title="x"/>';
      final segs = p.parse(content);
      expect(segs, hasLength(1));
      expect(segs.single, isA<MarkdownSegment>());
      expect((segs.single as MarkdownSegment).content, content);
    });

    test('chart with no segments produces no chart segment', () {
      final p = XmlTagParser();
      const content = '<pie-chart></pie-chart>';
      final segs = p.parse(content);
      // Either a markdown leftover or nothing — but no chart segment.
      expect(segs.whereType<PieChartSegment>(), isEmpty);
    });
  });

  group('XmlTagParser.parse — mixed content', () {
    test('preserves order: markdown → tag → markdown', () {
      final p = XmlTagParser();
      const content = '## Heading\n\n<rich-list><item title="x"/></rich-list>\n\nFooter text.';
      final segs = p.parse(content);
      expect(segs, hasLength(3));
      expect(segs[0], isA<MarkdownSegment>());
      expect((segs[0] as MarkdownSegment).content, contains('Heading'));
      expect(segs[1], isA<RichListSegment>());
      expect(segs[2], isA<MarkdownSegment>());
      expect((segs[2] as MarkdownSegment).content, contains('Footer'));
    });
  });
}
