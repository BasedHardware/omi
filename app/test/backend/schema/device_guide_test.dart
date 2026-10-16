import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/device_guide.dart';

void main() {
  group('DeviceGuide', () {
    test('should correctly initialize with all properties', () {
      final guide = DeviceGuide(
        deviceName: 'Test Device',
        title: 'Test Title',
        description: 'Test Description',
        instructions: 'Test Instructions',
        imagePath: 'test_image.png',
        videoPath: 'test_video.mp4',
        titleColor: Colors.blue,
        link: 'https://example.com',
        btName: 'Test BT Name',
      );

      expect(guide.deviceName, 'Test Device');
      expect(guide.title, 'Test Title');
      expect(guide.description, 'Test Description');
      expect(guide.instructions, 'Test Instructions');
      expect(guide.imagePath, 'test_image.png');
      expect(guide.videoPath, 'test_video.mp4');
      expect(guide.titleColor, Colors.blue);
      expect(guide.link, 'https://example.com');
      expect(guide.btName, 'Test BT Name');
    });
  });
}
