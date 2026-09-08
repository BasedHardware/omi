import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Maps a connected capture device to the `source` string the app sends on the
/// `/v4/listen` websocket (`?source=...`).
///
/// This value is the sole signal the backend uses to label a conversation's
/// provenance (`ConversationSource`). Getting it wrong is silent: audio still
/// streams and transcribes, but the conversation is mislabeled — e.g. Ray-Ban
/// Meta glasses would not be recognized as their own source, and the photo
/// pipeline's source-aware relabel (`resolve_photo_conversation_source`) would
/// not preserve `rayban_meta`.
///
/// Kept as a pure, exhaustive switch so a newly added [DeviceType] fails the
/// compile here (no `default`) and is caught by the unit test, rather than
/// silently streaming with a null/wrong source.
String? conversationSourceForDeviceType(DeviceType? type) {
  if (type == null) {
    return null;
  }
  switch (type) {
    case DeviceType.friendPendant:
      return 'friend_com';
    case DeviceType.omi:
      return 'omi';
    case DeviceType.openglass:
      return 'openglass';
    case DeviceType.fieldy:
      return 'fieldy';
    case DeviceType.bee:
      return 'bee';
    case DeviceType.plaud:
      return 'plaud';
    case DeviceType.appleWatch:
      return 'apple_watch';
    case DeviceType.limitless:
      return 'limitless';
    case DeviceType.raybanMeta:
      return 'rayban_meta';
  }
}
