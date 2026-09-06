#import "OmiDeviceControls.h"
#include <cassert>

int main() {
  @autoreleasepool {
    OmiFindPattern pattern;
    NSUInteger ticket = pattern.begin();
    assert(OmiFindPattern::level == 3 && OmiFindPattern::delayMs == 750);
    for (int index = 0; index < 3; index++) {
      assert(pattern.send(ticket));
      assert(!pattern.send(ticket));
      assert(!pattern.complete());
      assert(pattern.acknowledge(ticket));
      assert(!pattern.acknowledge(ticket));
      assert(pattern.complete() == (index == 2));
    }
    assert(!pattern.send(ticket));
    ticket = pattern.begin();
    assert(pattern.send(ticket));
    assert(pattern.acknowledge(ticket));
    pattern.cancel();
    assert(!pattern.send(ticket));
    assert(!pattern.acknowledge(ticket));
    NSUInteger replacement = pattern.begin();
    assert(!pattern.send(ticket));
    assert(pattern.send(replacement));
    pattern.cancel();
    assert(!pattern.acknowledge(replacement));
    const uint8_t mask[] = {128, 1, 0, 0};
    NSNumber *features = OmiDeviceFeatures([NSData dataWithBytes:mask length:4]);
    assert(features.unsignedIntValue == 384);
    assert(OmiDeviceFeatures([NSData dataWithBytes:mask length:3]) == nil);
    assert(OmiDeviceSettingSupported(features, @"ledBrightness"));
    assert(OmiDeviceSettingSupported(features, @"microphoneGain"));
    assert(!OmiDeviceSettingSupported(nil, @"ledBrightness"));
    assert(!OmiDeviceSettingSupported(@0, @"ledBrightness"));
    assert(!OmiDeviceSettingSupported(@128, @"microphoneGain"));
    assert(!OmiDeviceSettingSupported(features, @"firmware"));
    assert(OmiDeviceSettingMaximum(@"microphoneGain") == 8);
    assert(OmiDeviceSettingMaximum(@"ledBrightness") == 100);
    uint8_t valid = 8, invalid = 9;
    assert([OmiDeviceSettingValue(@"microphoneGain", [NSData dataWithBytes:&valid length:1]) isEqualToNumber:@8]);
    assert(OmiDeviceSettingValue(@"microphoneGain", [NSData dataWithBytes:&invalid length:1]) == nil);
    assert(OmiDeviceSettingValue(@"microphoneGain", [NSData data]) == nil);
  }
}
