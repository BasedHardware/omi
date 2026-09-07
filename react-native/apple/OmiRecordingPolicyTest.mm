#import "OmiRecordingPolicy.h"
static void require(BOOL value) { if (!value) abort(); }
int main() {
  @autoreleasepool {
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
