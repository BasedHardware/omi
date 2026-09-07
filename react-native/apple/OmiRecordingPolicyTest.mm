#import "OmiRecordingPolicy.h"
static void require(BOOL value) { if (!value) abort(); }
int main() {
  @autoreleasepool {
    NSDictionary *legacy = @{@"tokenUserId":@"existing-owner",@"idToken":@"synthetic",@"refreshToken":@"synthetic-refresh"};
    NSDictionary *initialized = OmiRecordingInitializeLogin(legacy);
    require([initialized[@"journalLogin"] length] > 0);
    require([initialized[@"tokenUserId"] isEqual:legacy[@"tokenUserId"]]);
    require([initialized[@"idToken"] isEqual:legacy[@"idToken"]]);
    require([OmiRecordingInitializeLogin(initialized)[@"journalLogin"] isEqual:initialized[@"journalLogin"]]);
    require(legacy[@"journalLogin"] == nil);
    require(OmiRecordingInitializeLogin(nil) == nil);
    NSDictionary *claims = @{@"aud":@"based-hardware",@"iss":@"https://securetoken.google.com/based-hardware",@"sub":@"existing-owner"};
    require([OmiRecordingLocalIdentity(initialized, claims)[@"uid"] isEqual:@"existing-owner"]);
    for (NSDictionary *change in @[@{@"aud":@"another-project"},@{@"iss":@"https://securetoken.google.com/another-project"},@{@"sub":@"other-owner"},@{@"user_id":@"other-owner"}]) {
      NSMutableDictionary *wrong = [claims mutableCopy]; [wrong addEntriesFromDictionary:change];
      require(OmiRecordingLocalIdentity(initialized, wrong) == nil);
    }
    require(OmiRecordingLocalIdentity(legacy, claims) == nil);
    for (NSNumber *status in @[@408, @429, @500, @503, @599]) require(OmiRecordingRetryableOwnershipStatus(status.integerValue));
    for (NSNumber *status in @[@200, @400, @401, @403, @409, @600]) require(!OmiRecordingRetryableOwnershipStatus(status.integerValue));
    NSDictionary *beforeForget = @{@"idToken":@"new-token", @"rememberedDevice":@{@"id":@"old-device"}};
    require(OmiRememberedRefreshSession(beforeForget, @{})[@"rememberedDevice"] == nil);
    NSDictionary *replacement = @{@"rememberedDevice":@{@"id":@"new-device"}};
    NSDictionary *merged = OmiRememberedRefreshSession(beforeForget, replacement);
    require([merged[@"rememberedDevice"] isEqual:replacement[@"rememberedDevice"]]);
    require([merged[@"idToken"] isEqual:@"new-token"]);
    require([OmiRememberedRefreshSession(beforeForget, beforeForget)[@"rememberedDevice"] isEqual:beforeForget[@"rememberedDevice"]]);
    require(OmiRememberedIdentity(@"device", @"Omi"));
    require(!OmiRememberedIdentity(nil, @"Omi"));
    require(!OmiRememberedIdentity(@1, @"Omi"));
    require(!OmiRememberedIdentity(@"device", @""));
    require(!OmiRememberedIdentity([@"x" stringByPaddingToLength:129 withString:@"x" startingAtIndex:0], @"Omi"));
    require(!OmiRememberedIdentity(@"device", [@"x" stringByPaddingToLength:257 withString:@"x" startingAtIndex:0]));
    require(OmiRememberedCurrent(1, 1, @"login", @"login", YES));
    require(!OmiRememberedCurrent(1, 2, @"login", @"login", YES));
    require(!OmiRememberedCurrent(1, 1, @"login", @"other", YES));
    require(!OmiRememberedCurrent(1, 1, @"login", nil, YES));
    require(!OmiRememberedCurrent(1, 1, @"login", @"login", NO));
    for (NSNumber *code in @[@(NSURLErrorTimedOut), @(NSURLErrorNotConnectedToInternet), @(NSURLErrorNetworkConnectionLost)])
      require(OmiRecordingOffline([NSError errorWithDomain:NSURLErrorDomain code:code.integerValue userInfo:nil]));
    for (NSNumber *code in @[@(NSURLErrorCancelled), @(NSURLErrorServerCertificateUntrusted), @(NSURLErrorBadURL)])
      require(!OmiRecordingOffline([NSError errorWithDomain:NSURLErrorDomain code:code.integerValue userInfo:nil]));
    require(!OmiRecordingOffline([NSError errorWithDomain:@"HTTP" code:401 userInfo:nil]));
    require(!OmiRecordingOffline([NSError errorWithDomain:@"HTTP" code:503 userInfo:nil]));
    require(OmiRecordingSameContext(@"login-a", @"login-a", @"origin-a", @"origin-a"));
    require(!OmiRecordingSameContext(@"login-a", @"login-b", @"origin-a", @"origin-a"));
    require(!OmiRecordingSameContext(@"login-a", @"login-a", @"origin-a", @"origin-b"));
    require(!OmiRecordingSameContext(@"login-a", nil, @"origin-a", @"origin-a"));
    puts("Apple recording offline fallback policy tests passed");
  }
}
