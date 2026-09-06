#import <Foundation/Foundation.h>

static BOOL OmiBleCallbackIsCurrent(id current, id callback) {
  return current != nil && current == callback;
}

static BOOL OmiBleSetupExpired(NSUInteger currentGeneration, NSUInteger expectedGeneration, BOOL pending) {
  return pending && currentGeneration == expectedGeneration;
}

static BOOL OmiBleRecordingReady(BOOL connected, BOOL notifying, BOOL hasCodec) {
  return connected && notifying && hasCodec;
}
