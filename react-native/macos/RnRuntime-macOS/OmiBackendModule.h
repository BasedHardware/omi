#import <React/RCTEventEmitter.h>

@interface OmiBackendModule : RCTEventEmitter <RCTBridgeModule>
- (void)rememberedDevice:(NSString *)action device:(NSDictionary *)device current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject;
- (void)prepareBleRecording:(NSDictionary *)device restoring:(BOOL)restoring current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject;
- (BOOL)appendBlePacket:(NSData *)packet codec:(NSNumber *)codec at:(NSNumber *)at sealed:(NSDictionary **)sealed;
- (NSDictionary *)stopBleRecording:(BOOL)forget;
- (void)rotateBleRecording;
- (NSString *)restorableBleDeviceId;
@end

// The validated OMI_V5_BACKEND_URL origin (https, allowed host, port 443 or
// loopback, bare path) or nil when unset/invalid. Shared so the auth module's
// desktop handoff and the backend module route through ONE validation.
NSURL *OmiValidatedV5BackendURLFromEnvironment(void);

// The effective software plane: the stored omi.backend.softwarePlane
// preference wins ("new"/"old"); when unset it defaults to "new" only if a
// stamped v5 origin is configured. Shared so auth's sign-in gate and the
// backend router can never disagree about which plane is active.
BOOL OmiSoftwarePlaneIsNew(void);
