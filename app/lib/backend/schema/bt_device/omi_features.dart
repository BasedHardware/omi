/// Feature flags for Omi device capabilities
/// Must match the firmware definitions in features.h
class OmiFeatures {
  static const int speaker = 1 << 0;
  static const int accelerometer = 1 << 1;
  static const int button = 1 << 2;
  static const int battery = 1 << 3;
  static const int usb = 1 << 4;
  static const int haptic = 1 << 5;
  static const int offlineStorage = 1 << 6;
  static const int ledDimming = 1 << 7;
  static const int micGain = 1 << 8;
}
