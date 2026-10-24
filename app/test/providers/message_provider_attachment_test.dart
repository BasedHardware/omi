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
  // earlier successfully uploaded selections and their uploadedFiles entries stay,
  // even when the failed file shares its path with an earlier selection.
  test('uploadFiles failure removes only the failed batch from the selection', () async {
    final provider = MessageProvider();
    final uploaded = File('/tmp/same.png');
    provider.selectedFiles.add(uploaded);
    provider.selectedFileTypes.add('image');
    provider.uploadedFiles.add(MessageFile('oai-1', null, 'same.png', 'image/png', 'ok-1', DateTime(2026), null));

    final failed = File('/tmp/same.png');
    provider.selectedFiles.add(failed);
    provider.selectedFileTypes.add('image');

    try {
      await provider.uploadFiles([failed], null);
    } catch (_) {}

    expect(provider.selectedFiles, [uploaded]);
    expect(provider.selectedFileTypes, ['image']);
    expect(provider.uploadedFiles.map((f) => f.id), ['ok-1']);
  });

  test('clearSelectedFile out-of-range or negative index is a no-op', () {
    final provider = MessageProvider();
    provider.uploadedFiles.add(MessageFile('oai-1', null, 'stale.png', 'image/png', 'stale-1', DateTime(2026), null));

    provider.clearSelectedFile(0);
    provider.clearSelectedFile(-1);

    expect(provider.selectedFiles, isEmpty);
    expect(provider.uploadedFiles.length, 1);
  });

  // Regression: a sent video showed a gray square because its clip path became the
  // bubble's image thumbnail. It now shows the sampled poster frame, and pairs each
  // upload with its own source even when uploads finish out of order.
  test('a sent video previews its poster frame, never the clip', () async {
    final clip = File('/tmp/run.mov');
    final photo = File('/tmp/photo.jpg');
    final video = MessageFile('', 'https://cdn/sheet.jpg', 'run.jpg', 'image/jpeg', 'vid-1', DateTime(2026), null,
        videoDurationSeconds: 12.4, localPreviewPath: '/tmp/omi-chat-video-posters/vid-1.jpg');
    final image = MessageFile('', null, 'photo.jpg', 'image/jpeg', 'img-1', DateTime(2026), null);
    final provider = MessageProvider(
      filesUploader: (files, {appId}) async => [for (final f in files) identical(f, clip) ? video : image],
    );
    provider.selectedFiles.addAll([clip, photo]);
    provider.selectedFileTypes.addAll(['video', 'image']);
    // The photo finishes uploading before the video.
    await provider.uploadFiles([photo], null);
    await provider.uploadFiles([clip], null);

    expect(provider.videoPosterFor(clip)?.path, '/tmp/omi-chat-video-posters/vid-1.jpg');

    provider.addMessageLocally('What do you see here?');

    final files = provider.messages.last.files;
    final sentVideo = files.firstWhere((f) => f.id == 'vid-1');
    final sentPhoto = files.firstWhere((f) => f.id == 'img-1');
    expect(sentVideo.mimeTypeToFileType(), 'video');
    expect(sentVideo.thumbnail, '/tmp/omi-chat-video-posters/vid-1.jpg');
    expect(sentPhoto.thumbnail, '/tmp/photo.jpg');
  });

  test('a video row from the server is typed as video and keeps its length', () {
    final file = MessageFile.fromJson({
      'id': 'vid-2',
      'name': 'clip.jpg',
      'mime_type': 'image/jpeg',
      'openai_file_id': 'oai',
      'created_at': '2026-10-22T00:00:00Z',
      'video': {'duration_seconds': 7.5},
    });

    expect(file.isVideo, isTrue);
    expect(file.mimeTypeToFileType(), 'video');
    expect(MessageFile.fromJson(file.toJson()).videoDurationSeconds, 7.5);
  });
}
