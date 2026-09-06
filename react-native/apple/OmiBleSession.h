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

typedef struct {
  BOOL armed;
  NSUInteger attempts;
  NSUInteger generation;
} OmiBleReconnectState;

static void OmiBleReconnectReady(OmiBleReconnectState *state) {
  state->armed = YES;
  state->attempts = 0;
  state->generation++;
}

static void OmiBleReconnectCancel(OmiBleReconnectState *state) {
  state->armed = NO;
  state->attempts = 0;
  state->generation++;
}

static NSInteger OmiBleReconnectDelay(OmiBleReconnectState *state) {
  if (!state->armed || state->attempts == 3) {
    OmiBleReconnectCancel(state);
    return -1;
  }
  state->generation++;
  return 1000 << state->attempts++;
}

static BOOL OmiBleReconnectAccepts(OmiBleReconnectState state, NSUInteger generation) {
  return state.armed && state.generation == generation;
}
