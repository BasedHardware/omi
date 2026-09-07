#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

typedef NSDictionary * _Nullable (^OmiRewindIdentity)(void);
typedef void (^OmiRewindFrameSource)(void (^completion)(CGImageRef _Nullable, NSString * _Nullable, NSString * _Nullable, NSError * _Nullable));
typedef void (^OmiRewindCaptureCompletion)(NSDictionary * _Nullable, NSError * _Nullable);

@interface OmiRewindCapture : NSObject
- (instancetype)initWithIdentity:(OmiRewindIdentity)identity root:(NSURL *)root authorityLock:(id)authorityLock;
- (instancetype)initWithIdentity:(OmiRewindIdentity)identity root:(NSURL *)root source:(OmiRewindFrameSource)source permission:(BOOL (^)(void))permission;
- (NSString *)requestCapturePermission;
- (BOOL)startCapture:(NSError **)error;
- (void)stopCapture;
- (void)captureFrame:(OmiRewindCaptureCompletion)completion;
- (void)invalidate;
@end
