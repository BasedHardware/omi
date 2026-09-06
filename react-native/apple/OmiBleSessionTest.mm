#import "OmiBleSession.h"
#include <cassert>

int main() {
  @autoreleasepool {
    assert(OmiBleRecordingReady(YES, YES, YES));
    assert(!OmiBleRecordingReady(YES, NO, YES));
    assert(!OmiBleRecordingReady(YES, YES, NO));
    assert(!OmiBleRecordingReady(NO, YES, YES));
    OmiBleReconnectState reconnect = {};
    assert(OmiBleReconnectDelay(&reconnect) == -1);
    OmiBleReconnectReady(&reconnect);
    assert(OmiBleReconnectDelay(&reconnect) == 1000);
    NSUInteger retry = reconnect.generation;
    assert(OmiBleReconnectAccepts(reconnect, retry));
    assert(OmiBleReconnectDelay(&reconnect) == 2000);
    assert(!OmiBleReconnectAccepts(reconnect, retry));
    assert(OmiBleReconnectDelay(&reconnect) == 4000);
    assert(OmiBleReconnectDelay(&reconnect) == -1);
    assert(!OmiBleReconnectAccepts(reconnect, reconnect.generation));
    OmiBleReconnectReady(&reconnect);
    assert(OmiBleReconnectDelay(&reconnect) == 1000);
    retry = reconnect.generation;
    OmiBleReconnectCancel(&reconnect);
    assert(!OmiBleReconnectAccepts(reconnect, retry));
    assert(OmiBleReconnectDelay(&reconnect) == -1);
    OmiBleReconnectReady(&reconnect);
    assert(!OmiBleReconnectAccepts(reconnect, retry));
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
