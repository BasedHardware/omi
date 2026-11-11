/// Static tripwire (not behavioral coverage): every share_plus call in lib/
/// must pass `sharePositionOrigin`.
///
/// share_plus throws `PlatformException(sharePositionOrigin: argument must be
/// set ...)` on iPad/macOS when the anchor is missing, and the throw is usually
/// the last await in a tap handler, so the button silently does nothing. The
/// helper fix (`shareSheetOrigin`) landed with three call sites still
/// unanchored (chat message share, action item share, daily summary share) —
/// this scan is what keeps a fourth from shipping.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('every Share call in lib/ passes sharePositionOrigin', () {
    final callPattern = RegExp(r'\b(Share\.share(XFiles)?|SharePlus\.instance\.share)\(');
    final violations = <String>[];

    for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart')) continue;
      final source = file.readAsStringSync();
      for (final match in callPattern.allMatches(source)) {
        final callEnd = _matchingParen(source, match.end - 1);
        final call = source.substring(match.start, callEnd);
        if (!call.contains('sharePositionOrigin')) {
          final line = source.substring(0, match.start).split('\n').length;
          violations.add('${file.path}:$line');
        }
      }
    }

    expect(violations, isEmpty,
        reason: 'pass `sharePositionOrigin: shareSheetOrigin(anchorKey)` (lib/utils/share_sheet.dart) to each call');
  });
}

int _matchingParen(String source, int openIndex) {
  var depth = 0;
  for (var i = openIndex; i < source.length; i++) {
    final c = source[i];
    if (c == '(') depth++;
    if (c == ')') {
      depth--;
      if (depth == 0) return i + 1;
    }
  }
  return source.length;
}
