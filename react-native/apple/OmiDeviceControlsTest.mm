#import "OmiDeviceControls.h"
#include <cassert>
#include <initializer_list>

int main() {
  @autoreleasepool {
    assert(!OmiButtonSupported(nil) && !OmiButtonSupported(@0) && OmiButtonSupported(@4));
    assert(!OmiButtonDoublePress(nil));
    uint8_t button[9] = {2};
    assert(OmiButtonDoublePress([NSData dataWithBytes:button length:8]));
    for (NSUInteger length : {0, 4, 7, 9}) assert(!OmiButtonDoublePress([NSData dataWithBytes:button length:length]));
    for (uint8_t action : {0, 1, 3, 4, 5, 255}) { button[0] = action; assert(!OmiButtonDoublePress([NSData dataWithBytes:button length:8])); }
    button[0] = 2;
    for (NSUInteger index = 1; index < 8; index++) { button[index] = 1; assert(!OmiButtonDoublePress([NSData dataWithBytes:button length:8])); button[index] = 0; }
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
    assert(OmiStorageSupported(@64));
    assert(!OmiStorageSupported(nil));
    assert(!OmiStorageSupported(@32));
    uint8_t status[] = {255,255,255,255, 1,0,0,0, 0,16,0,0, 1,0,0,0};
    NSDictionary *storage = OmiStorageStatus([NSData dataWithBytes:status length:16]);
    assert([storage[@"usedBytes"] unsignedLongLongValue] == 4294967295ULL);
    assert([storage[@"unreadPackets"] intValue] == 1);
    assert([storage[@"freeBytes"] intValue] == 4096);
    assert([storage[@"clockValid"] boolValue]);
    const NSUInteger invalidLengths[] = {0, 8, 15, 17};
    for (NSUInteger length : invalidLengths) assert(OmiStorageStatus([NSMutableData dataWithLength:length]) == nil);
    assert(OmiStorageStatus([NSMutableData dataWithLength:16]) == nil);
    status[12] = 2;
    assert(OmiStorageStatus([NSData dataWithBytes:status length:16]) == nil);
    status[12] = 0;
    assert(![OmiStorageStatus([NSData dataWithBytes:status length:16])[@"clockValid"] boolValue]);
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
