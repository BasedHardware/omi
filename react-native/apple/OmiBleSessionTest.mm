#import "OmiBleSession.h"
#include <cassert>

int main() {
  @autoreleasepool {
    assert(OmiBleRecordingReady(YES, YES, YES));
    assert(!OmiBleRecordingReady(YES, NO, YES));
    assert(!OmiBleRecordingReady(YES, YES, NO));
    assert(!OmiBleRecordingReady(NO, YES, YES));
    NSObject *first = [NSObject new];
    NSObject *second = [NSObject new];
    assert(OmiBleCallbackIsCurrent(first, first));
    assert(!OmiBleCallbackIsCurrent(nil, first));
    assert(!OmiBleCallbackIsCurrent(second, first));
    assert(!OmiBleCallbackIsCurrent(nil, nil));
    assert(OmiBleSetupExpired(1, 1, YES));
    assert(!OmiBleSetupExpired(2, 1, YES));
    assert(!OmiBleSetupExpired(1, 1, NO));
  }
}
