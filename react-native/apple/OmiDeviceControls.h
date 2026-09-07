#import <Foundation/Foundation.h>

static BOOL OmiButtonSupported(NSNumber *features) { return features != nil && (features.unsignedIntValue & 4U) != 0; }
static BOOL OmiButtonDoublePress(NSData *data) {
  if (data.length != 8) return NO;
  const uint8_t *bytes = (const uint8_t *)data.bytes;
  if (bytes[0] != 2) return NO;
  for (NSUInteger index = 1; index < 8; index++) if (bytes[index] != 0) return NO;
  return YES;
}

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

static BOOL OmiStorageSupported(NSNumber *features) {
  return features != nil && (features.unsignedIntValue & (1U << 6)) != 0;
}

static NSDictionary *OmiStorageStatus(NSData *data) {
  if (data.length != 16) return nil;
  const uint8_t *bytes = (const uint8_t *)data.bytes;
  uint64_t values[4] = {};
  for (NSUInteger field = 0; field < 4; field++) for (NSUInteger index = 0; index < 4; index++)
    values[field] |= (uint64_t)bytes[field * 4 + index] << (index * 8);
  if (values[3] > 1 || values[0] + values[2] == 0) return nil;
  return @{ @"usedBytes":@(values[0]), @"unreadPackets":@(values[1]), @"freeBytes":@(values[2]), @"clockValid":@(values[3] == 1) };
}

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
