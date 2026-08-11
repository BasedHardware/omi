import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/message_provider.dart';

void main() {
  // Regression: after a failed upload, uploadedFiles stays empty while selectedFiles
  // holds the picked file; removing the attachment threw RangeError on uploadedFiles.
  test('clearSelectedFile tolerates uploadedFiles shorter than selectedFiles', () {
    final provider = MessageProvider();
    provider.selectedFiles.add(File('/tmp/a.png'));
    provider.selectedFileTypes.add('image');

    provider.clearSelectedFile(0);

    expect(provider.selectedFiles, isEmpty);
    expect(provider.selectedFileTypes, isEmpty);
    expect(provider.uploadedFiles, isEmpty);
  });

  test('clearSelectedFile out-of-range index is a no-op', () {
    final provider = MessageProvider();

    provider.clearSelectedFile(0);

    expect(provider.selectedFiles, isEmpty);
  });
}
