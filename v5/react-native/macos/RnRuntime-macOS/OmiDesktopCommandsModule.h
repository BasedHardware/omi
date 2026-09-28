#import <React/RCTEventEmitter.h>

extern NSString *const OmiDesktopSearchCommandNotification;
extern NSString *const OmiDesktopAppearanceDidChangeNotification;

NSAppearanceName OmiPreferredDesktopAppearance(void);

@interface OmiDesktopCommandsModule : RCTEventEmitter <RCTBridgeModule>
@end
