#import <React/RCTEventEmitter.h>

@interface OmiBackendModule : RCTEventEmitter <RCTBridgeModule>
- (void)rememberedDevice:(NSString *)action device:(NSDictionary *)device current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject;
- (void)prepareBleRecording:(NSDictionary *)device restoring:(BOOL)restoring current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject;
- (BOOL)appendBlePacket:(NSData *)packet codec:(NSNumber *)codec at:(NSNumber *)at sealed:(NSDictionary **)sealed;
- (NSDictionary *)stopBleRecording:(BOOL)forget;
- (void)rotateBleRecording;
- (NSString *)restorableBleDeviceId;
@end
