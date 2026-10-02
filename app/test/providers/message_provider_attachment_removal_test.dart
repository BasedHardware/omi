import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';

MessageFile _uploaded(String id) => MessageFile('oai-$id', null, '$id.png', 'image/png', id, DateTime(2026), null);

void main() {
  test('an attachment removed while uploading is not sent with the next message', () async {
    final pending = Completer<List<MessageFile>?>();
    final provider = MessageProvider(filesUploader: (files, {appId}) => pending.future);
    final photo = File('/tmp/wrong.png');
    provider.selectedFiles.add(photo);
    provider.selectedFileTypes.add('image');

    final upload = provider.uploadFiles([photo], null);
    provider.clearSelectedFile(0);
    pending.complete([_uploaded('wrong')]);
    await upload;

    expect(provider.selectedFiles, isEmpty);
    expect(provider.uploadedFiles, isEmpty);
  });

  test('removing an attachment drops its own upload when uploads finish out of order', () async {
    final uploads = <String, Completer<List<MessageFile>?>>{};
    final provider = MessageProvider(
      filesUploader: (files, {appId}) => (uploads[files.single.path] = Completer<List<MessageFile>?>()).future,
    );
    final first = File('/tmp/first.png');
    final second = File('/tmp/second.png');
    provider.selectedFiles.addAll([first, second]);
    provider.selectedFileTypes.addAll(['image', 'image']);

    final firstUpload = provider.uploadFiles([first], null);
    final secondUpload = provider.uploadFiles([second], null);
    uploads[second.path]!.complete([_uploaded('second')]);
    await secondUpload;
    uploads[first.path]!.complete([_uploaded('first')]);
    await firstUpload;

    provider.clearSelectedFile(0);

    expect(provider.selectedFiles, [second]);
    expect(provider.uploadedFiles.map((f) => f.id), ['second']);
  });
}
