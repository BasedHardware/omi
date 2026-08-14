#import <RCTAppDelegate.h>
#import <Cocoa/Cocoa.h>

@interface AppDelegate : RCTAppDelegate

@property (nonatomic, strong, nullable) id omiWindowUpdateObserver;
@property (nonatomic, assign) BOOL omiWindowGeometryApplied;

@end
