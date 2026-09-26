#import <Foundation/Foundation.h>

typedef NSDictionary *_Nullable(^OmiAmbientIdentity)(void);
typedef void (^OmiAmbientPermissionHandler)(NSString *state);

@interface OmiAudioCapture : NSObject
- (instancetype)initWithIdentity:(OmiAmbientIdentity)identity root:(NSURL *)root;
- (void)requestMicrophonePermission:(OmiAmbientPermissionHandler)completion;
- (BOOL)startCapture:(NSError **)error;
- (void)stopCapture;
- (NSDictionary *)status;
- (void)invalidate;
@end
