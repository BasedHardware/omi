#import "OmiBleRecording.h"
#include <cassert>

static NSData *packet(uint16_t sequence, uint8_t fragment, uint8_t sample) {
  const uint8_t bytes[] = {(uint8_t)sequence, (uint8_t)(sequence >> 8), fragment, sample};
  return [NSData dataWithBytes:bytes length:sizeof(bytes)];
}
static NSArray *record(NSData *data) { return @[@"p", [data base64EncodedStringWithOptions:0]]; }
static NSArray *decoded(NSDictionary *journal) {
  NSMutableArray *result = [NSMutableArray array];
  for (NSString *entry in journal[@"entries"]) [result addObject:[NSJSONSerialization JSONObjectWithData:[entry dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil]];
  return result;
}

int main() {
  @autoreleasepool {
    NSString *tag = [@"omi-ble-recording-test-" stringByAppendingString:NSUUID.UUID.UUIDString];
    NSString *root = [NSTemporaryDirectory() stringByAppendingPathComponent:tag];
    __block NSString *login = @"login-one";
    NSDictionary *owner = @{@"login":login, @"origin":@"https://example.invalid/",
      @"ownerKey":[@"capture-owner-v1:" stringByAppendingString:[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0]],
      @"receipt":[NSString stringWithFormat:@"capture1.%@.%@", [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0], [@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0]]};
    NSDictionary *device = @{@"deviceId":@"omi-test", @"deviceName":@"Omi"};
    OmiRecordingJournals *journals = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return login; }];
    OmiBleRecording *capture = [[OmiBleRecording alloc] initWithJournals:journals owner:owner device:device];
    NSDictionary *sealed = nil;
    // No React bridge/listeners exist. Restored mid-frame bytes are skipped;
    // accepted packets are encrypted and readable immediately after the call.
    assert([capture receive:packet(65534, 2, 91) codec:@21 at:@1000 sealed:&sealed error:nil]);
    assert(capture.activeHandle == nil);
    assert([capture receive:packet(65535, 0, 7) codec:@21 at:@1010 sealed:&sealed error:nil]);
    NSString *first = capture.activeHandle;
    assert([decoded([journals read:first error:nil]) isEqual:@[record(packet(65535, 0, 7))]]);
    // Crossing the minute alone cannot cut an Opus frame. Counter rollover is
    // preserved; the next fragment-zero packet belongs to a new journal.
    assert([capture receive:packet(0, 1, 19) codec:@21 at:@61010 sealed:&sealed error:nil]);
    assert(sealed == nil && [capture.activeHandle isEqual:first]);
    assert([capture receive:packet(1, 0, 42) codec:@21 at:@61011 sealed:&sealed error:nil]);
    assert([sealed[@"handle"] isEqual:first]);
    assert(([decoded([journals read:first error:nil]) isEqual:@[record(packet(65535, 0, 7)), record(packet(0, 1, 19)), @[@"s"]]]));
    NSString *second = capture.activeHandle;
    assert(![first isEqual:second]);
    assert([[journals read:second error:nil][@"capturedAtMs"] isEqual:@61011]);
    [capture requestRotation];
    assert([capture receive:packet(2, 1, 81) codec:@21 at:@61012 sealed:&sealed error:nil]);
    assert(sealed == nil);
    assert([capture receive:packet(3, 0, 95) codec:@21 at:@61013 sealed:&sealed error:nil]);
    assert([sealed[@"handle"] isEqual:second]);
    NSString *third = capture.activeHandle;
    assert(![capture receive:packet(4, 0, 3) codec:@99 at:@61014 sealed:&sealed error:nil]);
    assert([decoded([journals read:third error:nil]) count] == 1);
    [capture requestRotation];
    assert([capture receive:packet(5, 0, 17) codec:@21 at:@61015 sealed:&sealed error:nil]);
    assert(sealed == nil && [capture.activeHandle isEqual:third]);
    assert([capture receive:packet(6, 0, 29) codec:@21 at:@61016 sealed:&sealed error:nil]);
    // A gap cannot disappear between independent server sessions. The old
    // journal retains both sides so the decoder can reject its missing packet.
    assert(([decoded([journals read:third error:nil]) isEqual:@[record(packet(3, 0, 95)), record(packet(5, 0, 17)), @[@"s"]]]));
    NSString *fourth = capture.activeHandle;
    // Existing accepted bytes survive account retirement, but the new owner
    // cannot append them or publish them under their own account.
    login = @"login-two";
    assert(![capture receive:packet(7, 0, 3) codec:@21 at:@61017 sealed:&sealed error:nil]);
    assert([capture seal:nil] == nil);
    [journals close];
    login = @"login-one";
    journals = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return login; }];
    assert([[journals list:owner error:nil] count] == 4);
    assert([decoded([journals read:fourth error:nil]) isEqual:@[record(packet(6, 0, 29))]]);
    [journals dispose];
    assert([NSFileManager.defaultManager removeItemAtPath:root error:nil]);
    assert(SecItemDelete((__bridge CFDictionaryRef)@{(__bridge id)kSecClass:(__bridge id)kSecClassKey,
      (__bridge id)kSecAttrApplicationTag:[tag dataUsingEncoding:NSUTF8StringEncoding],
      (__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom}) == errSecSuccess);
    puts("Native BLE recording: durable without JS, frame-aligned rotation, account retirement and restart passed");
  }
}
