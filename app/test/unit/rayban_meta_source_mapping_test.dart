import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/conversation_source_for_device.dart';

/// Guards the device -> `/v4/listen?source=` mapping.
///
/// This is the linchpin of capture provenance: the value returned here is what
/// the backend stores as `ConversationSource`. A silent regression (a device
/// mapping to the wrong string, or a new [DeviceType] falling through to null)
/// would still stream and transcribe audio, but every conversation from that
/// device would be mislabeled. For Ray-Ban Meta specifically, the wrong source
/// also breaks the photo pipeline's `resolve_photo_conversation_source`
/// preservation (it only keeps `rayban_meta`/`openglass`).
void main() {
  group('conversationSourceForDeviceType', () {
    test('maps Ray-Ban Meta glasses to rayban_meta', () {
      expect(conversationSourceForDeviceType(DeviceType.raybanMeta), 'rayban_meta');
    });

    test('null device yields null source', () {
      expect(conversationSourceForDeviceType(null), isNull);
    });

    test('every device type maps to its backend ConversationSource string', () {
      const expected = <DeviceType, String>{
        DeviceType.omi: 'omi',
        DeviceType.openglass: 'openglass',
        DeviceType.appleWatch: 'apple_watch',
        DeviceType.plaud: 'plaud',
        DeviceType.bee: 'bee',
        DeviceType.fieldy: 'fieldy',
        DeviceType.friendPendant: 'friend_com',
        DeviceType.limitless: 'limitless',
        DeviceType.raybanMeta: 'rayban_meta',
      };

      // Fails if a DeviceType is added without a mapping entry here, forcing the
      // author to decide its backend source instead of silently streaming null.
      expect(expected.keys.toSet(), DeviceType.values.toSet(),
          reason: 'a DeviceType is missing from the source-mapping contract');

      expected.forEach((type, source) {
        expect(conversationSourceForDeviceType(type), source, reason: 'wrong source for $type');
      });
    });
  });
}
