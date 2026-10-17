/// Read-time note repair. Never writes a conversation; numeric chat citations remain separate.
({String text, List<String> sourceIDs}) _repairPass(String input, Iterable<String> knownIDs) {
  final valid = knownIDs.toSet();
  final protected = <String, String>{};
  var prefix = '\uE000';
  while (input.contains(prefix)) {
    prefix += '\uE000';
  }
  String protect(String value) {
    final key = '$prefix${List.filled(protected.length, '\uE002').join()}\uE001';
    protected[key] = value;
    return key;
  }

  const marker = '\x00';
  var text = input.replaceAllMapped(
    RegExp(
      r'^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^[ \t]{0,3}\1[`~]*[ \t]*(?:\n|$)|(?![\s\S]))|(`+)(?!`)[\s\S]*?(?<!`)\2(?!`)',
      multiLine: true,
    ),
    (match) => protect(match[0]!),
  );
  final recovered = <String>[];
  String remove([List<String> ids = const []]) {
    recovered.addAll(ids);
    return marker;
  }

  String cleanSeparators(String value) => value
      .replaceAll(RegExp(r'[\x00\x01]'), '')
      .replaceAll(RegExp(r'^[\s,;]+|[\s,;]+$'), '')
      .replaceAllMapped(RegExp(r'([,;])(?:\s*[,;])+'), (match) => match[1]!);

  final linkPattern = RegExp(r'^\[([^\]\n]*)\]\(([^)\n]*)\)$');
  String unit(String value) {
    final link = linkPattern.firstMatch(value);
    if (link != null) {
      final label = link[1]!.trim();
      if (label.isEmpty) return remove();
      if (valid.contains(label)) return remove([label]);
      final destination = link[2]!.trim();
      final scheme = destination.contains(':') ? destination.split(':').first.toLowerCase() : '';
      return const ['http', 'https', 'mailto'].contains(scheme) ? protect(value) : label;
    }
    if (value.startsWith('(')) {
      final ids = value
          .substring(1, value.length - 1)
          .split(RegExp('[;,]'))
          .map((token) {
            final nested = linkPattern.firstMatch(token.trim());
            return nested == null ? token.trim() : nested[1]!.trim();
          })
          .where((token) => token.isNotEmpty)
          .toList();
      return ids.isNotEmpty && ids.every(valid.contains)
          ? remove(ids)
          : value.replaceAllMapped(
              RegExp(r'\[[^\[\]\n]*\]\([^\n)]*\)|[\[［【][^\[\]［］【】\n]*[\]］】]'), (match) => unit(match[0]!));
    }
    final content =
        value.substring(1, value.length - 1).replaceAll(RegExp('[\u200b\u200c\u200d\u2060\ufeff]'), '').trim();
    final tokens = content.split(RegExp(r'[\s,;]+')).where((token) => token.isNotEmpty).toList();
    if (tokens.isNotEmpty && tokens.every(valid.contains)) return remove(tokens);
    final header = content.split(RegExp(r'\s+'));
    if (header.length == 2 && valid.contains(header[0]) && RegExp(r'^[?]?[0-9A-Za-z]{1,3}$').hasMatch(header[1])) {
      return remove([header[0]]);
    }
    final mixedIDs = tokens.where(valid.contains).toList();
    if (mixedIDs.isNotEmpty) {
      recovered.addAll(mixedIDs);
      return cleanSeparators(
          content.replaceAllMapped(RegExp(r'[^\s,;]+'), (match) => valid.contains(match[0]) ? '' : match[0]!));
    }
    if (tokens.isEmpty ||
        RegExp(r'^(?:spk|speaker)[ _]\d+:?$', caseSensitive: false).hasMatch(content) ||
        RegExp(r'^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,95}|\^\d+)$').hasMatch(content)) {
      return remove();
    }
    return protect(value);
  }

  text = text.replaceAllMapped(
      RegExp(r'\[[^\[\]\n]*\]\([^\n)]*\)|(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)|[\[［【][^\[\]［］【】\n]*[\]］】]'),
      (match) => unit(match[0]!));
  final sorted = valid.toList()..sort((a, b) => b.length.compareTo(a.length));
  for (final id in sorted) {
    text = text.replaceAll(RegExp('(?<![\\w-])${RegExp.escape(id)}(?![\\w-])'), marker);
  }
  text = text.replaceAll(RegExp(r'\b(?:spk|speaker)[ _]\d+\b:?[ \t]*', caseSensitive: false), marker);
  while (true) {
    final cleaned = text.replaceAllMapped(RegExp(r'\([^()\n]*\)'), (match) {
      final value = match[0]!;
      if (!RegExp(r'[\x00\x01]').hasMatch(value)) return value;
      final content = cleanSeparators(value.substring(1, value.length - 1));
      return content.isEmpty ? '\x01' : '($content)';
    });
    if (cleaned == text) break;
    text = cleaned;
  }
  if (text.contains(marker)) {
    text = text
        .replaceAll(RegExp('$marker(?:[ \\t]*$marker)+'), marker)
        .replaceAll(RegExp('[ \\t]+$marker[ \\t]+'), ' ')
        .replaceAll(RegExp('[ \\t]+$marker(?=[,.;:]|\\n|\$)'), '')
        .replaceAll(RegExp('$marker[ \\t]+'), '')
        .replaceAll(marker, '')
        .trim();
  }
  if (text.contains('\x01')) text = text.replaceAll('\x01', '').trim();
  for (final entry in protected.entries.toList().reversed) {
    text = text.replaceAll(entry.key, entry.value);
  }
  return (text: text, sourceIDs: recovered.toSet().toList());
}

({String text, List<String> sourceIDs}) repairNoteCitations(String input, Iterable<String> knownIDs) {
  final ids = knownIDs.toList();
  final recovered = <String>[];
  var text = input;
  while (true) {
    final result = _repairPass(text, ids);
    recovered.addAll(result.sourceIDs);
    if (result.text == text) return (text: text, sourceIDs: recovered.toSet().toList());
    text = result.text;
  }
}
