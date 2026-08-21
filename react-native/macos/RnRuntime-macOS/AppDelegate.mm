#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"

#import <React/RCTBundleURLProvider.h>
#import <React/RCTUIKit.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  self.moduleName = @"RnRuntime";
  // You can add your custom initial props in the dictionary below.
  // They will be passed down to the ViewController used by React Native.
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

- (void)dressOmiWindow
{
  NSWindow *window = self.window;
  if (window == nil) {
    return;
  }

  // Inherit the system appearance. A hard-coded Aqua appearance makes the
  // transparent titlebar and material disagree with Dark Mode.
  window.appearance = nil;
  window.opaque = NO;
  window.backgroundColor = NSColor.clearColor;
  RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;
  rootView.backgroundColor = NSColor.clearColor;
  window.hasShadow = NO;
  window.styleMask |= NSWindowStyleMaskFullSizeContentView | NSWindowStyleMaskClosable |
      NSWindowStyleMaskMiniaturizable;
  window.titlebarAppearsTransparent = YES;
  window.titleVisibility = NSWindowTitleHidden;
  window.titlebarSeparatorStyle = NSTitlebarSeparatorStyleNone;
  // The app uses a transparent full-size titlebar, so the uncovered window ground is the drag
  // region. Controls continue to receive their normal input; this restores ordinary macOS window
  // movement without creating a React Native gesture layer.
  window.movableByWindowBackground = YES;
  window.level = NSNormalWindowLevel;
  window.hidesOnDeactivate = NO;
  window.contentMinSize = NSMakeSize(800.0, 680.0);
  if (!self.omiWindowGeometryApplied) {
    [window setContentSize:NSMakeSize(960.0, 700.0)];
    [window center];
    self.omiWindowGeometryApplied = YES;
  }
  NSWindowCollectionBehavior behavior = window.collectionBehavior;
  behavior |= NSWindowCollectionBehaviorMoveToActiveSpace | NSWindowCollectionBehaviorFullScreenAuxiliary;
  behavior &= ~NSWindowCollectionBehaviorFullScreenPrimary;
  window.collectionBehavior = behavior;
  [window standardWindowButton:NSWindowCloseButton].hidden = NO;
  [window standardWindowButton:NSWindowMiniaturizeButton].hidden = NO;
  [window standardWindowButton:NSWindowZoomButton].hidden = NO;
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

/// This method controls whether the `concurrentRoot`feature of React18 is turned on or off.
///
/// @see: https://reactjs.org/blog/2022/03/29/react-v18.html
/// @note: This requires to be rendering on Fabric (i.e. on the New Architecture).
/// @return: `true` if the `concurrentRoot` feature is enabled. Otherwise, it returns `false`.
- (BOOL)concurrentRootEnabled
{
#ifdef RN_FABRIC_ENABLED
  return true;
#else
  return false;
#endif
}

@end
