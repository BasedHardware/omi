#import <Foundation/Foundation.h>

typedef void (^RCTPromiseResolveBlock)(id);
typedef void (^RCTPromiseRejectBlock)(NSString *, NSString *, NSError *);
@protocol RCTBridgeModule <NSObject>
@end
@class RCTBridge;
@interface RCTEventEmitter : NSObject
@property(nonatomic, strong) RCTBridge *bridge;
- (void)invalidate;
- (void)sendEventWithName:(NSString *)name body:(id)body;
@end
#define RCT_EXPORT_MODULE(name)
#define RCT_REMAP_METHOD(name, method) - (void)method
