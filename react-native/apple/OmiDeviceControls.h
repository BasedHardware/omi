#import <Foundation/Foundation.h>

struct OmiFindPattern {
  static constexpr int level = 3;
  static constexpr int delayMs = 750;
  NSUInteger generation = 0;
  int sent = 0;
  bool active = false;
  bool awaiting = false;
  void cancel() { generation++; active = false; awaiting = false; sent = 0; }
  NSUInteger begin() { cancel(); active = true; return generation; }
  bool send(NSUInteger ticket) {
    if (ticket != generation || !active || awaiting || sent >= 3) return false;
    sent++; awaiting = true; return true;
  }
  bool acknowledge(NSUInteger ticket) {
    if (ticket != generation || !active || !awaiting) return false;
    awaiting = false; return true;
  }
  bool complete() const { return active && sent == 3 && !awaiting; }
};

static NSNumber *OmiDeviceFeatures(NSData *data) {
  if (data.length != 4) return nil;
  const uint8_t *bytes = (const uint8_t *)data.bytes;
  uint32_t value = 0;
  for (NSUInteger index = 0; index < 4; index++) value |= (uint32_t)bytes[index] << (index * 8);
  return @(value);
}

static NSInteger OmiDeviceSettingMaximum(NSString *setting) {
  return [setting isEqualToString:@"ledBrightness"] ? 100 : [setting isEqualToString:@"microphoneGain"] ? 8 : -1;
}

static BOOL OmiDeviceSettingSupported(NSNumber *features, NSString *setting) {
  NSInteger bit = [setting isEqualToString:@"ledBrightness"] ? 7 : [setting isEqualToString:@"microphoneGain"] ? 8 : -1;
  return features != nil && bit >= 0 && (features.unsignedIntValue & (1U << bit)) != 0;
}

static NSNumber *OmiDeviceSettingValue(NSString *setting, NSData *data) {
  if (data.length != 1) return nil;
  NSUInteger value = ((const uint8_t *)data.bytes)[0];
  NSInteger maximum = OmiDeviceSettingMaximum(setting);
  return maximum >= 0 && value <= (NSUInteger)maximum ? @(value) : nil;
}
