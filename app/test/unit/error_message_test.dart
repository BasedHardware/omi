import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/error_message.dart';

void main() {
  test('lifts the detail out of an API error body', () {
    final error = Exception(
      'Failed to rebuild knowledge graph: {"detail":"Canonical knowledge graph state is derived from '
      'canonical memories and cannot be deleted or rebuilt directly."}',
    );

    expect(
      readableError(error),
      'Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly.',
    );
  });

  test('reads a PlatformException message instead of its dump', () {
    final error = PlatformException(
      code: 'Unexpected security result code',
      message: 'The specified item already exists in the keychain.',
      details: -25299,
    );

    expect(readableError(error), 'The specified item already exists in the keychain.');
  });

  test('falls back to the platform code when the message is empty', () {
    final error = PlatformException(code: 'channel-error', message: '  ');

    expect(readableError(error), 'channel-error');
  });

  test('strips the exception prefix from a plain message', () {
    expect(readableError(Exception('Device is not connected')), 'Device is not connected');
    expect(readableError(const FormatException('Unexpected end of input')), 'Unexpected end of input');
  });

  test('keeps a body it cannot parse rather than inventing one', () {
    expect(readableError('offline'), 'offline');
    expect(readableError(Exception('Failed to save: {not json}')), 'Failed to save: {not json}');
  });

  test('truncates a long body to one snackbar line', () {
    final result = readableError(Exception('x' * 400));

    expect(result.length, 160);
    expect(result.endsWith('…'), isTrue);
  });

  test('renders a null error as empty rather than the word null', () {
    expect(readableError(null), isEmpty);
  });
}
