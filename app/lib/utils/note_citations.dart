/// Protected-unit keys: a prefix the input does not contain, the unit's index in base 254 over
/// U+E002..U+E0FF, then U+E001. Private-use characters match no repair pattern, and the keys stay
/// short however many units a note holds.
const _keyBase = 254;
String _keyDigits(int index) {
  final codes = <int>[];
  do {
    codes.insert(0, 0xE002 + index % _keyBase);
    index ~/= _keyBase;
  } while (index > 0);
  return String.fromCharCodes(codes);
}

/// Keep the transcript iterable lazy until a bracket/link needs exact membership.
/// Plain titles only materialize IDs actually present in the text for the bare-ID
/// removal pass; they do not allocate and sort the entire transcript's ID set.
class _KnownIDs {
  _KnownIDs(this.source);

  final Iterable<String> source;
  Set<String>? _materialized;

  bool contains(String id) => (_materialized ??= source.where((id) => id.isNotEmpty).toSet()).contains(id);

  List<String> matching(String text) =>
      text.isEmpty ? [] : (_materialized ?? source).where((id) => id.isNotEmpty && text.contains(id)).toList();
}

/// Read-time note repair. Never writes a conversation; numeric chat citations remain separate.
({String text, List<String> sourceIDs}) _repairPass(String input, _KnownIDs valid) {
  final protected = <String, String>{};
  var prefix = '\uE000';
  while (input.contains(prefix)) {
    prefix += '\uE000';
  }
  String protect(String value) {
    final key = '$prefix${_keyDigits(protected.length)}\uE001';
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
          content.replaceAllMapped(RegExp(r'[^\s,;]+'), (match) => valid.contains(match[0]!) ? '' : match[0]!));
    }
    if (tokens.isEmpty ||
        _titleSpeaker.hasMatch(content) ||
        RegExp(r'^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,95}|\^\d+)$').hasMatch(content)) {
      return remove();
    }
    return protect(value);
  }

  text = text.replaceAllMapped(
      RegExp(r'\[[^\[\]\n]*\]\([^\n)]*\)|(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)|[\[［【][^\[\]［］【】\n]*[\]］】]'),
      (match) => unit(match[0]!));
  final sorted = valid.matching(text)..sort((a, b) => b.length.compareTo(a.length));
  for (final id in sorted) {
    // Home rows normally contain none of their transcript's hundreds/thousands
    // of IDs. Do not compile Unicode boundary patterns for absent literals:
    // regexp parsing/canonicalization alone can consume the scene watchdog.
    if (!text.contains(id)) continue;
    text =
        text.replaceAll(RegExp('(?<![\\p{L}\\p{N}_-])${RegExp.escape(id)}(?![\\p{L}\\p{N}_-])', unicode: true), marker);
  }
  // Word boundaries and digits are Unicode, as in Python generation and Swift (ICU): an ID or
  // speaker label glued to CJK text is part of a word, not a citation, and `Speaker_١٢` is a label.
  text = text.replaceAll(_bareSpeaker, marker);
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
  // One pass, restoring nested units (a link label that held a code span) recursively.
  final keyPattern = RegExp('$prefix[\uE002-\uE0FF]+\uE001');
  String restore(String value) => value.replaceAllMapped(keyPattern, (match) {
        final unit = protected[match[0]!];
        return unit == null ? match[0]! : restore(unit);
      });
  text = restore(text);
  return (text: text, sourceIDs: recovered.toSet().toList());
}

({String text, List<String> sourceIDs}) repairNoteCitations(String input, Iterable<String> knownIDs) {
  // An id-less segment reaches here as '' (TranscriptSegment.fromGenerated); as a pattern it would
  // match between every two non-word characters and the cleanup would then eat the whitespace
  // around each match. Web and macOS drop empty ids before calling their repair; do the same.
  return _repairNoteCitations(input, _KnownIDs(knownIDs));
}

({String text, List<String> sourceIDs}) _repairNoteCitations(String input, _KnownIDs ids) {
  final recovered = <String>[];
  var text = input;
  while (true) {
    final result = _repairPass(text, ids);
    recovered.addAll(result.sourceIDs);
    if (result.text == text) return (text: text, sourceIDs: recovered.toSet().toList());
    text = result.text;
  }
}

// Citation-shaped bracket tokens in a title: a transcript segment UUID, the compact `s01234` form,
// or a `^1` footnote marker.
final _titleCitationToken = RegExp(
    r'^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|s[0-9]{4,}|\^[0-9]+)$',
    caseSensitive: false);
final _titleSpeaker = RegExp(r'^(?:spk|speaker)[ _]\p{Nd}+:?$', caseSensitive: false, unicode: true);
final _bareSpeaker = RegExp(r'(?<![\p{L}\p{N}_])(?:spk|speaker)[ _]\p{Nd}+(?![\p{L}\p{N}_]):?[ \t]*',
    caseSensitive: false, unicode: true);
const _titleOpen = '[［【';
const _titleClose = ']］】';
const _slotBase = 0xF00; // slot digits U+E100..U+EFFF

typedef _TitleGroup = ({int start, int end, bool nested});

/// Balanced bracket groups that are not inside another closed group.
List<_TitleGroup> _titleBracketGroups(String input) {
  final groups = <_TitleGroup>[];
  var stack = <({int start, List<_TitleGroup> inner})>[];
  void flush() {
    for (final open in stack) {
      groups.addAll(open.inner);
    }
    stack = [];
  }

  for (var i = 0; i < input.length; i++) {
    final c = input[i];
    if (c == '\n') {
      flush();
    } else if (_titleOpen.contains(c)) {
      stack.add((start: i, inner: <_TitleGroup>[]));
    } else if (_titleClose.contains(c) && stack.isNotEmpty) {
      final open = stack.removeLast();
      final group = (start: open.start, end: i + 1, nested: open.inner.isNotEmpty);
      if (stack.isNotEmpty) {
        stack.last.inner.add(group);
      } else {
        groups.add(group);
      }
    }
  }
  flush();
  return groups..sort((a, b) => a.start.compareTo(b.start));
}

bool _isTitleCitation(String content, _KnownIDs known) {
  final bare = content.replaceAll(RegExp('[​‌‍⁠﻿]'), '').trim();
  if (_titleSpeaker.hasMatch(bare)) return true;
  return bare
      .split(RegExp(r'[\s,;]+'))
      .where((token) => token.isNotEmpty)
      .every((token) => _titleCitationToken.hasMatch(token) || known.contains(token));
}

String _slotDigits(int index) {
  final codes = <int>[];
  do {
    codes.insert(0, 0xE100 + index % _slotBase);
    index ~/= _slotBase;
  } while (index > 0);
  return String.fromCharCodes(codes);
}

/// Read-time repair of a conversation title (web `presentableNoteTitle`). Titles keep ordinary
/// bracketed words ("Project [Q3]"): only bracket units made of known IDs, citation-shaped IDs or a
/// speaker label are debris, and a nested group ("[Project [s01234]]") is kept whole. Everything else
/// the note repair does applies as for any note text.
String presentableNoteTitle(String text, Iterable<String> knownIDs) {
  final known = _KnownIDs(knownIDs);
  var mask = '';
  while (text.contains(mask)) {
    mask += '';
  }
  final kept = <String>[];
  final masked = StringBuffer();
  var last = 0;
  for (final group in _titleBracketGroups(text)) {
    final unit = text.substring(group.start, group.end);
    if (!group.nested && _isTitleCitation(unit.substring(1, unit.length - 1), known)) continue;
    masked
      ..write(text.substring(last, group.start))
      ..write('$mask${_slotDigits(kept.length)}');
    kept.add(unit);
    last = group.end;
  }
  masked.write(text.substring(last));
  return _repairNoteCitations(masked.toString(), known).text.replaceAllMapped(
    RegExp('${RegExp.escape(mask)}([-]+)'),
    (match) {
      var index = 0;
      for (final digit in match[1]!.codeUnits) {
        index = index * _slotBase + digit - 0xE100;
      }
      return index < kept.length ? kept[index] : match[0]!;
    },
  );
}
