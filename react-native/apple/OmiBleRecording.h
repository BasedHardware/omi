#import "OmiRecordingJournals.h"

// All methods run on OmiBackend's journal queue. A BLE notification is durable
// before returning to CoreBluetooth; neither the React bridge nor a network
// request participates in the append path.
@interface OmiBleRecording : NSObject
@property(nonatomic, readonly) NSString *activeHandle;
- (instancetype)initWithJournals:(OmiRecordingJournals *)journals owner:(NSDictionary *)owner device:(NSDictionary *)device;
- (BOOL)receive:(NSData *)packet codec:(NSNumber *)codec at:(NSNumber *)at sealed:(NSDictionary **)sealed error:(NSError **)error;
- (NSDictionary *)seal:(NSError **)error;
- (void)requestRotation;
@end

@implementation OmiBleRecording {
  OmiRecordingJournals *_journals;
  NSDictionary *_owner;
  NSDictionary *_device;
  NSDictionary *_active;
  NSUInteger _bytes;
  NSUInteger _packets;
  uint16_t _lastSequence;
  BOOL _rotationRequested;
}
- (instancetype)initWithJournals:(OmiRecordingJournals *)journals owner:(NSDictionary *)owner device:(NSDictionary *)device {
  self = [super init];
  if (self) { _journals = journals; _owner = [owner copy]; _device = [device copy]; }
  return self;
}
- (NSString *)activeHandle { return _active[@"handle"]; }
- (void)requestRotation { _rotationRequested = YES; }
- (NSDictionary *)seal:(NSError **)error {
  NSDictionary *sealed = _active;
  if (sealed != nil && [_journals append:self.activeHandle entry:@"[\"s\"]" error:error] == nil) return nil;
  _active = nil;
  _bytes = 0;
  _packets = 0;
  _rotationRequested = NO;
  return sealed;
}
- (BOOL)receive:(NSData *)packet codec:(NSNumber *)codec at:(NSNumber *)at sealed:(NSDictionary **)sealed error:(NSError **)error {
  if (sealed != NULL) *sealed = nil;
  NSUInteger format = codec.unsignedIntegerValue;
  if (packet.length < 4 || packet.length > 512 ||
      (format != 1 && format != 20 && format != 21) || !OmiRecordingCapturedAtValid(at)) return OmiRecordingError(error);
  const uint8_t *bytes = (const uint8_t *)packet.bytes;
  uint16_t sequence = (uint16_t)(bytes[0] | (bytes[1] << 8));
  BOOL startsFrame = bytes[2] == 0;
  if (_active != nil && ![_active[@"codec"] isEqual:codec]) return OmiRecordingError(error);
  // Keep the same packet framing as foreground upload. Never split an Opus
  // frame. Reserve the maximum frame size and fragment count before the limits.
  BOOL rotate = _rotationRequested || _bytes >= 8388608 - 62208 || _packets >= 65536 - 256 ||
      (_active != nil && at.doubleValue - [_active[@"capturedAtMs"] doubleValue] >= 60000);
  if (_active != nil && startsFrame && rotate && sequence == (uint16_t)(_lastSequence + 1)) {
    NSDictionary *completed = [self seal:error];
    if (completed == nil) return NO;
    if (sealed != NULL) *sealed = completed;
  }
  if (_active == nil) {
    // A restored subscription may resume mid-frame. Wait for a real boundary
    // rather than manufacturing the missing prefix of that frame.
    if (!startsFrame) return YES;
    NSMutableDictionary *input = [_device mutableCopy];
    input[@"codec"] = codec;
    input[@"capturedAtMs"] = at;
    _active = [_journals create:_owner input:input error:error];
    if (_active == nil) return NO;
  }
  if (_bytes + packet.length > 8388608 || _packets >= 65536) return OmiRecordingError(error);
  NSData *json = [NSJSONSerialization dataWithJSONObject:@[@"p", [packet base64EncodedStringWithOptions:0]] options:0 error:error];
  NSString *entry = json == nil ? nil : [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
  if (entry == nil || [_journals append:self.activeHandle entry:entry error:error] == nil) return NO;
  _bytes += packet.length;
  _packets++;
  _lastSequence = sequence;
  return YES;
}
@end
