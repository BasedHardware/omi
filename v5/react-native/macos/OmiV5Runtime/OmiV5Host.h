#import <AppKit/AppKit.h>

NS_ASSUME_NONNULL_BEGIN

@protocol OmiHostSessionProvider <NSObject>
- (void)fetchIDTokenForcingRefresh:(BOOL)force
                        completion:(void (^)(NSString *_Nullable token, NSError *_Nullable error))completion;
- (nullable NSDictionary<NSString *, NSString *> *)currentIdentity;
- (void)hostSignOutRequested;
@end

@protocol OmiHostCaptureController <NSObject>
- (NSDictionary *)captureState;
- (void)setScreenCaptureOn:(BOOL)on completion:(void (^)(BOOL accepted, NSString *_Nullable reason))completion;
- (void)setAudioRecordingOn:(BOOL)on completion:(void (^)(BOOL accepted, NSString *_Nullable reason))completion;
- (nullable NSString *)rewindDatabasePath;
@end

@protocol OmiHostShellDelegate <NSObject>
- (void)requestClassicInterface;
- (void)reportError:(NSString *)message stack:(nullable NSString *)stack isFatal:(BOOL)isFatal;
- (void)trackEvent:(NSString *)name properties:(nullable NSDictionary<NSString *, id> *)properties;
@end

@interface OmiV5Host : NSObject
+ (void)registerSessionProvider:(id<OmiHostSessionProvider>)provider;
+ (void)registerCaptureController:(id<OmiHostCaptureController>)controller;
+ (void)registerShellDelegate:(id<OmiHostShellDelegate>)delegate;
+ (void)captureStateDidChange;
+ (void)sessionDidChange;
+ (NSView *)makeRootViewWithInitialProperties:(NSDictionary *)initialProperties;
@end

NS_ASSUME_NONNULL_END
