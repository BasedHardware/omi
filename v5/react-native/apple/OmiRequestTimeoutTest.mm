#import "OmiRequestTimeout.h"
#include <cassert>

int main() {
  @autoreleasepool {
    NSURL *url = [NSURL URLWithString:@"https://example.test/v1/device-sessions/id/transcribe?retry=1"];
    assert(OmiRequestTimeout(@"POST", url) == 150);
    assert(OmiRequestTimeout(@"GET", url) == 60);
    assert(OmiRequestTimeout(@"POST", [NSURL URLWithString:@"https://example.test/v1/device-sessions/id/complete"]) == 60);
    assert(OmiRequestTimeout(@"POST", [NSURL URLWithString:@"https://example.test/v1/device-sessions//transcribe"]) == 60);
  }
}
