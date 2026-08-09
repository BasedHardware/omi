#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface OmiNativeBoundaryBridge : NSObject
+ (NSString *)capabilities;
+ (NSString *)normalizePacket:(NSString *)raw;
@end

NS_ASSUME_NONNULL_END
