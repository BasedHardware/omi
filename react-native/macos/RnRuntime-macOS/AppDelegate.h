#import <RCTAppDelegate.h>
#import <Cocoa/Cocoa.h>

@interface AppDelegate : RCTAppDelegate

@property (nonatomic, strong, nullable) id omiWindowUpdateObserver;
@property (nonatomic, strong, nullable) id omiWindowDragMonitor;
@property (nonatomic, strong, nullable) NSVisualEffectView *omiWindowGlass;
@property (nonatomic, strong, nullable) NSTitlebarAccessoryViewController *omiTitlebarAccessory;
@property (nonatomic, assign) BOOL omiWindowGeometryApplied;

@end
