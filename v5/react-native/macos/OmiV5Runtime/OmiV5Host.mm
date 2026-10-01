#import "OmiV5Host.h"

#import <CoreText/CoreText.h>
#import <React/RCTDevLoadingViewSetEnabled.h>
#import <RCTRootViewFactory.h>

@implementation OmiV5Host

static id<OmiHostSessionProvider> sessionProvider;
static id<OmiHostCaptureController> captureController;
static id<OmiHostShellDelegate> shellDelegate;
static RCTRootViewFactory *rootFactory;

+ (void)registerSessionProvider:(id<OmiHostSessionProvider>)provider
{
  if (![provider conformsToProtocol:@protocol(OmiHostSessionProvider)]) { return; }
  sessionProvider = provider;
}
+ (void)registerCaptureController:(id<OmiHostCaptureController>)controller
{
  if (![controller conformsToProtocol:@protocol(OmiHostCaptureController)]) { return; }
  captureController = controller;
}
+ (void)registerShellDelegate:(id<OmiHostShellDelegate>)delegate
{
  if (![delegate conformsToProtocol:@protocol(OmiHostShellDelegate)]) { return; }
  shellDelegate = delegate;
}
+ (void)captureStateDidChange {}
+ (void)sessionDidChange {}

+ (NSView *)makeRootViewWithInitialProperties:(NSDictionary *)initialProperties
{
  if (!NSThread.isMainThread || ![initialProperties[@"hostMode"] boolValue]) {
    @throw [NSException exceptionWithName:NSInvalidArgumentException
                                   reason:@"An embedded root needs hostMode on the main thread"
                                 userInfo:nil];
  }
  RCTDevLoadingViewSetEnabled(NO);

  if (rootFactory == nil) {
    NSBundle *bundle = [NSBundle bundleForClass:self];
    NSURL *fontURL = [bundle URLForResource:@"MaterialSymbolsRounded" withExtension:@"ttf"];
    if (fontURL != nil) {
      CTFontManagerRegisterFontsForURL((__bridge CFURLRef)fontURL, kCTFontManagerScopeProcess, NULL);
    }
    NSURL *bundleURL = [bundle URLForResource:@"main" withExtension:@"jsbundle"];
    // The local runtime is built in Release mode to embed a reproducible JS
    // bundle. Metro is permitted only for the shipping app's dev bundle IDs.
    NSString *hostID = NSBundle.mainBundle.bundleIdentifier ?: @"";
    BOOL developmentHost = [hostID isEqualToString:@"com.omi.desktop-dev"] ||
        ([hostID hasPrefix:@"com.omi."] && ![hostID hasPrefix:@"com.omi.computer-macos"]);
    NSString *metroPort = developmentHost ? NSProcessInfo.processInfo.environment[@"OMI_V5_METRO_PORT"] : nil;
    NSInteger port = metroPort.integerValue;
    if (port > 0 && port <= 65535) {
      bundleURL = [NSURL URLWithString:[NSString stringWithFormat:
          @"http://localhost:%ld/index.bundle?platform=macos&dev=true&minify=false", (long)port]];
    }
    if (bundleURL == nil) {
      @throw [NSException exceptionWithName:NSInternalInconsistencyException
                                     reason:@"OmiV5Runtime has no embedded main.jsbundle"
                                   userInfo:nil];
    }
    RCTRootViewFactoryConfiguration *configuration =
        [[RCTRootViewFactoryConfiguration alloc] initWithBundleURL:bundleURL newArchEnabled:NO];
    rootFactory = [[RCTRootViewFactory alloc] initWithConfiguration:configuration];
  }
  return [rootFactory viewWithModuleName:@"RnRuntime" initialProperties:initialProperties];
}

@end
