#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"

#import <React/RCTBundleURLProvider.h>
#import <React/RCTUIKit.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>

static const CGFloat OmiTrafficLightLeading = 16.0;
static const CGFloat OmiTrafficLightSpacing = 8.0;
static const CGFloat OmiTrafficLightChromeHeight = 52.0;

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  self.moduleName = @"RnRuntime";
  self.initialProps = @{};
  NSString *metroPort = NSProcessInfo.processInfo.environment[@"OMI_METRO_PORT"];
  if (metroPort.integerValue > 0 && metroPort.integerValue <= 65535) {
    [RCTBundleURLProvider sharedSettings].jsLocation = [NSString stringWithFormat:@"localhost:%@", metroPort];
  }
  self.dependencyProvider = [RCTAppDependencyProvider new];

  [super applicationDidFinishLaunching:notification];
  [self dressOmiWindow];
  __weak AppDelegate *weakSelf = self;
  self.omiWindowUpdateObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:NSWindowDidUpdateNotification
                                                       object:self.window
                                                        queue:NSOperationQueue.mainQueue
                                                   usingBlock:^(__unused NSNotification *note) {
    [weakSelf dressOmiWindow];
  }];
  [self installDesktopSearchCommand];
  [self installOmiWindowDragMonitor];
}

- (void)applicationWillTerminate:(NSNotification *)notification
{
  if (self.omiWindowUpdateObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiWindowUpdateObserver];
    self.omiWindowUpdateObserver = nil;
  }
  if (self.omiWindowDragMonitor != nil) {
    [NSEvent removeMonitor:self.omiWindowDragMonitor];
    self.omiWindowDragMonitor = nil;
  }
  [super applicationWillTerminate:notification];
}

- (void)installOmiWindowGlass:(NSWindow *)window
{
  RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;
  if (self.omiWindowGlass == nil) {
    self.omiWindowGlass = [[NSVisualEffectView alloc] initWithFrame:rootView.bounds];
    self.omiWindowGlass.material = NSVisualEffectMaterialUnderWindowBackground;
    self.omiWindowGlass.blendingMode = NSVisualEffectBlendingModeBehindWindow;
    self.omiWindowGlass.state = NSVisualEffectStateActive;
    self.omiWindowGlass.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  }
  self.omiWindowGlass.frame = rootView.bounds;
  if (self.omiWindowGlass.superview != rootView) {
    [rootView addSubview:self.omiWindowGlass positioned:NSWindowBelow relativeTo:nil];
  }
}

- (void)installOmiTitlebarAccessory:(NSWindow *)window
{
  if (self.omiTitlebarAccessory != nil) {
    return;
  }
  NSView *spacer = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 0, OmiTrafficLightChromeHeight)];
  NSTitlebarAccessoryViewController *accessory = [[NSTitlebarAccessoryViewController alloc] init];
  accessory.view = spacer;
  accessory.layoutAttribute = NSLayoutAttributeTop;
  self.omiTitlebarAccessory = accessory;
  [window addTitlebarAccessoryViewController:accessory];
}

- (void)dressOmiWindow
{
  NSWindow *window = self.window;
  if (window == nil) {
    return;
  }

  window.appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];
  window.opaque = NO;
  window.backgroundColor = NSColor.clearColor;
  RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;
  rootView.appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];
  rootView.backgroundColor = NSColor.clearColor;
  window.hasShadow = NO;
  window.styleMask = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
      NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable |
      NSWindowStyleMaskFullSizeContentView;
  window.titlebarAppearsTransparent = YES;
  window.titleVisibility = NSWindowTitleHidden;
  window.title = @"";
  window.toolbarStyle = NSWindowToolbarStyleUnified;
  window.titlebarSeparatorStyle = NSTitlebarSeparatorStyleNone;
  window.movableByWindowBackground = NO;
  window.level = NSNormalWindowLevel;
  window.hidesOnDeactivate = NO;
  window.contentMinSize = NSMakeSize(800.0, 680.0);
  if (!self.omiWindowGeometryApplied) {
    [window setContentSize:NSMakeSize(900.0, 700.0)];
    [window center];
    self.omiWindowGeometryApplied = YES;
  }
  NSWindowCollectionBehavior behavior = window.collectionBehavior;
  behavior |= NSWindowCollectionBehaviorMoveToActiveSpace | NSWindowCollectionBehaviorFullScreenAuxiliary;
  behavior &= ~NSWindowCollectionBehaviorFullScreenPrimary;
  window.collectionBehavior = behavior;
  [self installOmiWindowGlass:window];
  [self installOmiTitlebarAccessory:window];
  [window standardWindowButton:NSWindowCloseButton].hidden = NO;
  [window standardWindowButton:NSWindowMiniaturizeButton].hidden = NO;
  [window standardWindowButton:NSWindowZoomButton].hidden = NO;
  [self positionOmiTrafficLights];
}

- (void)positionOmiTrafficLights
{
  NSWindow *window = self.window;
  NSButton *closeButton = [window standardWindowButton:NSWindowCloseButton];
  NSButton *miniaturizeButton = [window standardWindowButton:NSWindowMiniaturizeButton];
  NSButton *zoomButton = [window standardWindowButton:NSWindowZoomButton];
  if (closeButton == nil || closeButton.superview == nil) {
    return;
  }
  closeButton.hidden = NO;
  miniaturizeButton.hidden = NO;
  zoomButton.hidden = NO;
  NSView *container = closeButton.superview;
  CGFloat buttonWidth = NSWidth(closeButton.frame);
  CGFloat buttonHeight = NSHeight(closeButton.frame);
  CGFloat y = NSHeight(container.bounds) - OmiTrafficLightChromeHeight +
      floor((OmiTrafficLightChromeHeight - buttonHeight) / 2.0);
  CGFloat x = OmiTrafficLightLeading;
  for (NSButton *button in @[ closeButton, miniaturizeButton, zoomButton ]) {
    NSRect frame = button.frame;
    frame.origin = NSMakePoint(x, y);
    button.frame = frame;
    x += buttonWidth + OmiTrafficLightSpacing;
  }
}

- (void)installOmiWindowDragMonitor
{
  if (self.omiWindowDragMonitor != nil) {
    return;
  }
  __weak AppDelegate *weakSelf = self;
  self.omiWindowDragMonitor =
      [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskLeftMouseDown
                                            handler:^NSEvent *(NSEvent *event) {
    AppDelegate *strongSelf = weakSelf;
    if (strongSelf == nil || ![strongSelf omiWindowGroundDragEvent:event]) {
      return event;
    }
    [strongSelf.window performWindowDragWithEvent:event];
    return nil;
  }];
}

- (BOOL)omiWindowGroundDragEvent:(NSEvent *)event
{
  NSWindow *window = self.window;
  if (window == nil || event.window != window || event.clickCount > 1) {
    return NO;
  }
  NSView *contentView = window.contentView;
  NSView *frameView = contentView.superview;
  if (contentView == nil || frameView == nil) {
    return NO;
  }
  NSView *hitView = [frameView hitTest:event.locationInWindow];
  if (hitView == nil || ![hitView isDescendantOf:contentView]) {
    return NO;
  }
  for (NSView *view = hitView; view != nil; view = view.superview) {
    if ([view isKindOfClass:NSControl.class] || [view isKindOfClass:NSText.class] ||
        [view isKindOfClass:NSScrollView.class] || !view.mouseDownCanMoveWindow) {
      return NO;
    }
    if (view == contentView) {
      break;
    }
  }
  return YES;
}

- (void)installDesktopSearchCommand
{
  NSMenu *mainMenu = NSApplication.sharedApplication.mainMenu;
  NSMenuItem *editItem = [mainMenu itemWithTitle:@"Edit"];
  NSMenu *editMenu = editItem.submenu;
  if (editMenu == nil) {
    editItem = [[NSMenuItem alloc] initWithTitle:@"Edit" action:nil keyEquivalent:@""];
    editMenu = [[NSMenu alloc] initWithTitle:@"Edit"];
    editItem.submenu = editMenu;
    [mainMenu addItem:editItem];
  }
  NSMenuItem *searchItem = [[NSMenuItem alloc] initWithTitle:@"Search"
                                                      action:@selector(focusOmiSearch:)
                                               keyEquivalent:@"k"];
  searchItem.keyEquivalentModifierMask = NSEventModifierFlagCommand;
  searchItem.target = self;
  [editMenu addItem:searchItem];
}

- (void)focusOmiSearch:(id)sender
{
  [NSNotificationCenter.defaultCenter postNotificationName:OmiDesktopSearchCommandNotification
                                                      object:nil];
}

- (NSURL *)sourceURLForBridge:(RCTBridge *)bridge
{
  return [self bundleURL];
}

- (NSURL *)bundleURL
{
#if DEBUG
  return [[RCTBundleURLProvider sharedSettings] jsBundleURLForBundleRoot:@"index"];
#else
  return [[NSBundle mainBundle] URLForResource:@"main" withExtension:@"jsbundle"];
#endif
}

- (BOOL)concurrentRootEnabled
{
#ifdef RN_FABRIC_ENABLED
  return true;
#else
  return false;
#endif
}

@end
