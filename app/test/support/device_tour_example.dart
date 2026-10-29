import 'package:flutter_test/flutter_test.dart';

/// The example sentence the device tour's speaking step shows on its second line, without quote marks:
/// what an owner says when they follow the instruction.
String deviceTourExample(String subtitle) {
  final lines = subtitle.split('\n');
  expect(lines, hasLength(2), reason: 'the subtitle is a lead line, then the quoted example');
  return lines.last.replaceAll(RegExp(r'^[^\p{L}\p{N}]+|[^\p{L}\p{N}.。]+$', unicode: true), '');
}
