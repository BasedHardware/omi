import 'package:markdown/markdown.dart' as md;

String nativeRichBlockText(Map<String, Object> block) {
  if (block['kind'] == 'code' || block['kind'] == 'image') return block['text'] as String;
  final values = block['kind'] == 'table'
      ? (block['cells'] as List<List<String>>).expand((cells) => cells)
      : [block['text'] as String];
  final parser = md.Document(extensionSet: md.ExtensionSet.gitHubFlavored, encodeHtml: false);
  return values.map((value) => parser.parseInline(value).map((node) => node.textContent).join()).join('\n');
}

Map<String, String> nativeRichTextLinks(String source) {
  final links = <String, String>{};
  void visit(md.Node node) {
    if (node is! md.Element) return;
    final href = node.attributes['href'];
    if (node.tag == 'a' && href != null && href.isNotEmpty) {
      links[Uri.tryParse(href)?.toString() ?? href] = href;
    }
    for (final child in node.children ?? <md.Node>[]) {
      visit(child);
    }
  }

  final document = md.Document(extensionSet: md.ExtensionSet.gitHubFlavored, encodeHtml: false);
  for (final node in document.parseLines(source.split('\n'))) {
    visit(node);
  }
  return links;
}

/// A presentation projection of the same Markdown source used by the Flutter reader.
/// Links remain in their original source; no API, authentication or content owner is added.
List<Map<String, Object>> nativeRichText(String source) {
  final document = md.Document(extensionSet: md.ExtensionSet.gitHubFlavored, encodeHtml: false);
  final blocks = <Map<String, Object>>[];
  String inline(md.Node node) {
    if (node is md.Text) return node.text.replaceAllMapped(RegExp(r'[\\`*_\[\]]'), (m) => '\\${m[0]}');
    final element = node as md.Element;
    final text = (element.children ?? []).map(inline).join();
    return switch (element.tag) {
      'strong' => '**$text**',
      'em' => '*$text*',
      'del' => '~~$text~~',
      'code' => '`${element.textContent.replaceAll('`', '\\`')}`',
      'a' => '[$text](${element.attributes['href'] ?? ''})',
      'br' => '\n',
      'input' => element.attributes.containsKey('checked') ? '☑ ' : '☐ ',
      _ => text,
    };
  }

  void visit(md.Node node, {int indent = 0, String prefix = '', bool quote = false}) {
    if (node is md.Text) {
      if (node.text.isNotEmpty) {
        blocks.add({'kind': quote ? 'quote' : 'text', 'text': inline(node), 'indent': indent, 'prefix': prefix});
      }
      return;
    }
    final element = node as md.Element;
    final children = element.children ?? [];
    if (element.tag == 'ul' || element.tag == 'ol') {
      var number = int.tryParse(element.attributes['start'] ?? '') ?? 1;
      for (final child in children) {
        visit(child, indent: indent, prefix: element.tag == 'ol' ? '${number++}.' : '•', quote: quote);
      }
    } else if (element.tag == 'li') {
      var first = true;
      var text = '';
      void flush() {
        if (text.isEmpty) return;
        blocks.add({'kind': quote ? 'quote' : 'text', 'text': text, 'indent': indent, 'prefix': first ? prefix : ''});
        first = false;
        text = '';
      }

      for (final child in children) {
        final block =
            child is md.Element && ['p', 'ul', 'ol', 'blockquote', 'pre', 'table', 'hr', 'img'].contains(child.tag);
        if (!block) {
          text += inline(child);
          continue;
        }
        flush();
        final nested = ['ul', 'ol'].contains(child.tag);
        visit(child, indent: nested ? indent + 1 : indent, prefix: first && !nested ? prefix : '', quote: quote);
        if (!nested) first = false;
      }
      flush();
    } else if (element.tag == 'blockquote') {
      for (final child in children) {
        visit(child, indent: indent, quote: true);
      }
    } else if (element.tag == 'pre') {
      blocks.add({'kind': 'code', 'text': element.textContent, 'indent': indent, 'prefix': prefix});
    } else if (element.tag == 'hr') {
      blocks.add({'kind': 'rule', 'text': '', 'indent': indent, 'prefix': prefix});
    } else if (element.tag == 'img') {
      blocks.add({
        'kind': 'image',
        'text': element.attributes['alt'] ?? '',
        'uri': element.attributes['src'] ?? '',
        'indent': indent,
        'prefix': prefix
      });
    } else if (element.tag == 'table') {
      final rows = <List<String>>[];
      void row(md.Node item) {
        if (item is! md.Element) return;
        if (item.tag == 'tr') {
          rows.add((item.children ?? []).map(inline).toList());
        } else {
          for (final child in item.children ?? <md.Node>[]) {
            row(child);
          }
        }
      }

      row(element);
      blocks.add({'kind': 'table', 'text': '', 'cells': rows, 'indent': indent, 'prefix': prefix});
    } else if (RegExp(r'^h[1-6]$').hasMatch(element.tag)) {
      blocks.add({
        'kind': 'heading',
        'text': children.map(inline).join(),
        'level': int.parse(element.tag[1]),
        'indent': indent,
        'prefix': prefix
      });
    } else if (element.tag == 'p' && children.any((child) => child is md.Element && child.tag == 'img')) {
      var text = '';
      for (final child in children) {
        if (child is md.Element && child.tag == 'img') {
          if (text.isNotEmpty) {
            blocks.add({'kind': quote ? 'quote' : 'text', 'text': text, 'indent': indent, 'prefix': prefix});
          }
          text = '';
          visit(child, indent: indent);
        } else {
          text += inline(child);
        }
      }
      if (text.isNotEmpty) {
        blocks.add({'kind': quote ? 'quote' : 'text', 'text': text, 'indent': indent, 'prefix': prefix});
      }
    } else {
      blocks.add(
          {'kind': quote ? 'quote' : 'text', 'text': children.map(inline).join(), 'indent': indent, 'prefix': prefix});
    }
  }

  for (final node in document.parseLines(source.split('\n'))) {
    visit(node);
  }
  return blocks;
}
