import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';
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

  // Regression: a failed upload batch must only remove itself from the tray —
  // earlier successfully uploaded selections and their uploadedFiles entries stay.
  test('uploadFiles failure removes only the failed batch from the selection', () async {
    final provider = MessageProvider();
    provider.selectedFiles.add(File('/tmp/uploaded_ok.png'));
    provider.selectedFileTypes.add('image');
    provider.uploadedFiles
        .add(MessageFile('oai-1', null, 'uploaded_ok.png', 'image/png', 'ok-1', DateTime(2026), null));

    final failed = File('/tmp/failed.png');
    provider.selectedFiles.add(failed);
    provider.selectedFileTypes.add('image');

    try {
      await provider.uploadFiles([failed], null);
    } catch (_) {}

    expect(provider.selectedFiles.map((f) => f.path), ['/tmp/uploaded_ok.png']);
    expect(provider.selectedFileTypes, ['image']);
    expect(provider.uploadedFiles.map((f) => f.id), ['ok-1']);
  });

  test('clearSelectedFile out-of-range index is a no-op', () {
    final provider = MessageProvider();

    provider.clearSelectedFile(0);

    expect(provider.selectedFiles, isEmpty);
  });
}
