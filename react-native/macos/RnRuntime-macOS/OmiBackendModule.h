#import <React/RCTEventEmitter.h>

@interface OmiBackendModule : RCTEventEmitter <RCTBridgeModule>
- (void)rememberedDevice:(NSString *)action device:(NSDictionary *)device current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject;
@end
