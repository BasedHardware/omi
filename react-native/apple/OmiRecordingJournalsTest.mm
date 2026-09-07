#import "OmiRecordingJournals.h"

static void require(BOOL value) { if (!value) abort(); }
int main() {
  @autoreleasepool {
    NSString *identifier = NSUUID.UUID.UUIDString;
    NSString *root = [NSTemporaryDirectory() stringByAppendingPathComponent:identifier];
    NSString *tag = [@"omi-journal-test-" stringByAppendingString:identifier];
    __block NSString *login = @"login-one";
    NSDictionary *owner = @{ @"ownerKey":[@"capture-owner-v1:" stringByAppendingString:[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0]],
      @"receipt":[NSString stringWithFormat:@"capture1.%@.%@", [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0], [@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0]], @"origin":@"https://example.invalid/", @"login":login };
    OmiRecordingJournals *manager = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return login; }];
    NSError *error = nil;
    NSDictionary *created = [manager create:owner input:@{@"deviceId":@"omi-test", @"codec":@21} error:&error];
    require(created != nil);
    NSString *handle = created[@"handle"];
    require([manager append:handle entry:@"[\"p\",\"AAAB\"]" error:&error] != nil);
    require([manager ownerForRequest:handle request:@{@"method":@"POST", @"path":@"/v1/device-sessions", @"body":@"null"} error:&error] == nil);
    require([manager ownerForRequest:handle request:@{@"method":@"POST", @"path":@"/v1/device-sessions", @"body":NSNull.null} error:&error] == nil);
    NSString *body = [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:@{@"captureId":handle, @"deviceId":@"omi-test", @"codec":@21} options:0 error:nil] encoding:NSUTF8StringEncoding];
    NSDictionary *request = @{@"method":@"POST", @"path":@"/v1/device-sessions", @"body":body};
    require([manager ownerForRequest:handle request:request error:&error] != nil);
    NSString *session = NSUUID.UUID.UUIDString.lowercaseString;
    NSString *responseBody = [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:@{@"session":@{@"id":session, @"deviceId":@"omi-test", @"codec":@21}} options:0 error:nil] encoding:NSUTF8StringEncoding];
    require([manager acknowledgeOpen:handle request:request response:@{@"status":@201, @"body":responseBody} error:&error]);
    [manager close];
    manager = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return login; }];
    NSArray *listed = [manager list:owner error:&error];
    require(listed.count == 1 && [listed[0][@"entries"] count] == 0 && [listed[0][@"sessionId"] isEqual:session]);
    require([[manager read:handle error:&error][@"entries"] count] == 1);
    require([manager ownerForRequest:handle request:@{@"method":@"POST", @"path":[NSString stringWithFormat:@"/v1/device-sessions/%@/audio", session]} error:&error] != nil);
    require([manager ownerForRequest:handle request:@{@"method":@"POST", @"path":@"/v1/device-sessions/other/audio"} error:&error] == nil);
    require([manager ownerForRequest:handle request:@{@"method":@"POST", @"path":[NSString stringWithFormat:@"/v1/device-sessions/%@/../other/audio", session]} error:&error] == nil);
    login = @"login-two";
    require([manager read:handle error:&error] == nil);
    NSMutableDictionary *other = [owner mutableCopy]; other[@"login"] = login;
    require([[manager list:other error:&error] count] == 0);
    login = @"login-one";
    require([[manager list:owner error:&error] count] == 1);
    require([manager remove:handle error:&error]);
    [manager close];
    require([NSFileManager.defaultManager removeItemAtPath:root error:nil]);
    require(SecItemDelete((__bridge CFDictionaryRef)@{(__bridge id)kSecClass:(__bridge id)kSecClassKey, (__bridge id)kSecAttrApplicationTag:[tag dataUsingEncoding:NSUTF8StringEncoding], (__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom}) == errSecSuccess);
    puts("Apple recording journal ownership and persisted acknowledgement tests passed");
  }
}
