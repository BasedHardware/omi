#import <React/RCTBridgeModule.h>
#import "OmiAuthModule.h"
#import "OmiRewindStore.h"
#import "../../apple/OmiRewindCapture.h"

@interface OmiRewindModule : NSObject <RCTBridgeModule>
@property(nonatomic, strong) OmiRewindStore *shipping;
@property(nonatomic, strong) OmiRewindStore *captured;
@property(atomic) BOOL disposed;
@property(nonatomic, strong) OmiRewindCapture *capture;
@property(nonatomic, strong) dispatch_queue_t ioQueue;
@end
@implementation OmiRewindModule
RCT_EXPORT_MODULE(OmiRewind)
+ (BOOL)requiresMainQueueSetup { return NO; }
- (dispatch_queue_t)methodQueue {
  static dispatch_queue_t queue;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ queue = dispatch_queue_create("omi.rewind.read", DISPATCH_QUEUE_SERIAL); });
  return queue;
}
- (instancetype)init {
  if ((self = [super init])) {
    _ioQueue = dispatch_queue_create("omi.rewind.storage", DISPATCH_QUEUE_SERIAL);
    NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
    NSString *bundle = NSBundle.mainBundle.bundleIdentifier;
    if (support != nil && bundle.length > 0) {
      _shipping = [[OmiRewindStore alloc] initWithRoot:[support stringByAppendingPathComponent:@"Omi/users"] identity:^{ return OmiAuthLocalHistoryIdentity(); }];
      NSString *own = [[[support stringByAppendingPathComponent:bundle] stringByAppendingPathComponent:@"Rewind"] stringByAppendingPathComponent:@"users"];
      _captured = [[OmiRewindStore alloc] initWithRoot:own identity:^{ return OmiAuthLocalHistoryIdentity(); }];
      _capture = [[OmiRewindCapture alloc] initWithIdentity:^{ return OmiAuthLocalHistoryIdentity(); } root:[NSURL fileURLWithPath:own.stringByDeletingLastPathComponent] authorityLock:OmiAuthKeychainLock()];
    }
  }
  return self;
}
- (void)invalidate { [self.capture invalidate]; self.disposed = YES; self.shipping.disposed = YES; self.captured.disposed = YES; }
RCT_REMAP_METHOD(requestCapturePermission,
                 requestCapturePermissionWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  dispatch_async(dispatch_get_main_queue(), ^{
    if (self.disposed || self.capture == nil) { reject(@"OMI_REWIND_UNAVAILABLE", @"Rewind is unavailable", nil); return; }
    resolve([self.capture requestCapturePermission]);
  });
}
RCT_REMAP_METHOD(startCapture,
                 startCaptureWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSError *error = nil;
  if (self.disposed || self.capture == nil || ![self.capture startCapture:&error]) { reject(error.domain ?: @"OMI_REWIND_UNAVAILABLE", @"Capture could not start", nil); return; }
  resolve(nil);
}
RCT_REMAP_METHOD(stopCapture,
                 stopCaptureWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self.capture stopCapture]; resolve(nil);
}
RCT_REMAP_METHOD(captureFrame,
                 captureFrameWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if (self.disposed || self.capture == nil) { reject(@"OMI_REWIND_UNAVAILABLE", @"Rewind is unavailable", nil); return; }
  NSDictionary *identity = OmiAuthLocalHistoryIdentity();
  [self.capture captureFrame:^(NSDictionary *result, NSError *error) {
    if (self.disposed || ![identity isEqual:OmiAuthLocalHistoryIdentity()]) { reject(@"OMI_REWIND_OWNER_CHANGED", @"Rewind account changed", nil); return; }
    if (result == nil) { reject(error.domain ?: @"OMI_REWIND_UNAVAILABLE", @"Capture could not finish", nil); return; }
    resolve(result);
  }];
}
RCT_REMAP_METHOD(listFrames,
                 listFrames:(NSDictionary *)input
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSDictionary *requestedIdentity = OmiAuthLocalHistoryIdentity();
  dispatch_async(self.ioQueue, ^{
    if (requestedIdentity == nil) { reject(@"OMI_REWIND_AUTH", @"Sign in to view Rewind", nil); return; }
    if (self.disposed || ![requestedIdentity isEqual:OmiAuthLocalHistoryIdentity()]) { reject(@"OMI_REWIND_OWNER_CHANGED", @"Rewind account changed", nil); return; }

  NSString *source = input[@"source"] ?: @"shipping";
  if (![@[@"shipping",@"captured"] containsObject:source]) { reject(@"OMI_REWIND_INVALID_REQUEST", @"Rewind source is invalid", nil); return; }
  OmiRewindStore *store = [source isEqual:@"shipping"] ? self.shipping : self.captured;
  NSDictionary *identity = OmiAuthLocalHistoryIdentity();
  if (identity == nil) { reject(@"OMI_REWIND_AUTH", @"Sign in to view Rewind", nil); return; }
  if (self.disposed || store == nil) { reject(@"OMI_REWIND_UNAVAILABLE", @"Rewind is unavailable", nil); return; }
  NSMutableDictionary *request = [input mutableCopy];
  NSString *prefix = [source stringByAppendingString:@":"];
  if ([request[@"cursor"] isKindOfClass:NSString.class]) {
    if (![request[@"cursor"] hasPrefix:prefix]) { reject(@"OMI_REWIND_STALE_CURSOR", @"Rewind page changed", nil); return; }
    request[@"cursor"] = [request[@"cursor"] substringFromIndex:prefix.length];
  }
  NSError *error = nil; NSDictionary *result = [store list:request error:&error];
  NSString *database = [[store.root stringByAppendingPathComponent:identity[@"uid"]] stringByAppendingPathComponent:@"omi.db"];
  struct stat attributes = {};
  BOOL absent = lstat(database.fileSystemRepresentation, &attributes) != 0 && errno == ENOENT;
  if (result == nil && [source isEqual:@"captured"] && [error.domain isEqual:@"OMI_REWIND_UNAVAILABLE"] && absent) result = @{@"frames":@[],@"nextCursor":NSNull.null};
  if (self.disposed || ![identity isEqual:OmiAuthLocalHistoryIdentity()]) { reject(@"OMI_REWIND_OWNER_CHANGED", @"Rewind account changed", nil); return; }
  if (result == nil) { reject(error.domain ?: @"OMI_REWIND_UNAVAILABLE", @"Rewind could not be loaded", nil); return; }
  NSMutableArray *frames = [NSMutableArray array];
  for (NSDictionary *row in result[@"frames"]) { NSMutableDictionary *frame = [row mutableCopy]; frame[@"id"] = [prefix stringByAppendingString:row[@"id"]]; [frames addObject:frame]; }
  NSString *cursor = [result[@"nextCursor"] isKindOfClass:NSString.class] ? [prefix stringByAppendingString:result[@"nextCursor"]] : nil;
  resolve(@{@"frames":frames,@"nextCursor":cursor ?: NSNull.null});
  });
}
RCT_REMAP_METHOD(readFrame,
                 readFrame:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSDictionary *requestedIdentity = OmiAuthLocalHistoryIdentity();
  dispatch_async(self.ioQueue, ^{
    if (requestedIdentity == nil) { reject(@"OMI_REWIND_AUTH", @"Sign in to view Rewind", nil); return; }
    if (self.disposed || ![requestedIdentity isEqual:OmiAuthLocalHistoryIdentity()]) { reject(@"OMI_REWIND_OWNER_CHANGED", @"Rewind account changed", nil); return; }

  if (![identifier isKindOfClass:NSString.class]) { reject(@"OMI_REWIND_INVALID_REQUEST", @"Rewind frame is invalid", nil); return; }
  BOOL shipping = [identifier hasPrefix:@"shipping:"], captured = [identifier hasPrefix:@"captured:"];
  if (!shipping && !captured) { reject(@"OMI_REWIND_INVALID_REQUEST", @"Rewind frame is invalid", nil); return; }
  OmiRewindStore *store = shipping ? self.shipping : self.captured;
  NSDictionary *identity = OmiAuthLocalHistoryIdentity();
  if (identity == nil) { reject(@"OMI_REWIND_AUTH", @"Sign in to view Rewind", nil); return; }
  if (self.disposed || store == nil) { reject(@"OMI_REWIND_UNAVAILABLE", @"Rewind is unavailable", nil); return; }
  NSError *error = nil;
  NSDictionary *result = [store read:[identifier substringFromIndex:9] error:&error];
  if (self.disposed || ![identity isEqual:OmiAuthLocalHistoryIdentity()]) { reject(@"OMI_REWIND_OWNER_CHANGED", @"Rewind account changed", nil); return; }
  if (result == nil) { reject(error.domain ?: @"OMI_REWIND_FRAME_UNAVAILABLE", @"Rewind frame could not be loaded", nil); return; }
  NSMutableDictionary *value = [result mutableCopy]; value[@"id"] = identifier; resolve(value);
  });
}
@end
