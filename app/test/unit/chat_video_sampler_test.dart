import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/chat_video_sampler.dart';

void main() {
  test('phone and camera clips are chat videos; photos and documents are not', () {
    for (final path in ['/a/clip.mp4', '/a/IMG_0001.MOV', '/a/x.m4v', '/a/x.3gp', '/a/x.webm']) {
      expect(isChatVideo(path), isTrue, reason: path);
    }
    for (final path in ['/a/photo.jpg', '/a/doc.pdf', '/a/voice.m4a', '/a/noext']) {
      expect(isChatVideo(path), isFalse, reason: path);
    }
  });

  test('desktop and test hosts have no native sampler, so the clip uploads whole', () async {
    expect(await ChatVideoSampler.sample(File('/a/clip.mp4')), isNull);
  });
}
