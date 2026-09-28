#import "../RnRuntime-macOS/OmiAuthMobileCallback.h"
#include <cassert>

int main() {
  @autoreleasepool {
    assert(OmiAuthMobileCallbackIsValid(
        [NSURL URLWithString:@"omi-rnruntime://auth/callback?code=local-test&state=expected"], @"expected"));
    for (NSString *value in @[
      @"omi://auth/callback?code=local-test&state=expected",
      @"https://auth/callback?code=local-test&state=expected",
      @"omi-rnruntime://other/callback?code=local-test&state=expected",
      @"omi-rnruntime://user@auth/callback?code=local-test&state=expected",
      @"omi-rnruntime://auth:443/callback?code=local-test&state=expected",
      @"omi-rnruntime://auth/%63allback?code=local-test&state=expected",
      @"omi-rnruntime://auth/callback?code=local-test&state=expected#fragment",
      @"omi-rnruntime://auth/callback?code=local-test&state=wrong",
      @"omi-rnruntime://auth/callback?code=local-test&state=expected&state=expected",
      @"omi-rnruntime://auth/callback?code=local-test&code=duplicate&state=expected",
      @"omi-rnruntime://auth/callback?state=expected",
      @"omi-rnruntime://auth/callback?code=&state=expected",
      @"omi-rnruntime://auth/callback?code=local-test&state=expected&error=denied"
    ]) {
      assert(!OmiAuthMobileCallbackIsValid([NSURL URLWithString:value], @"expected"));
    }
    assert(!OmiAuthMobileCallbackIsValid(nil, @"expected"));
    puts("Apple mobile OAuth callback validation passed");
  }
}
