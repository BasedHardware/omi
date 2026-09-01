#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"
#import "OmiGlassPanelView.h"

#import <React/RCTBundleURLProvider.h>
#import <React/RCTUIKit.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>
#import <objc/runtime.h>

static const CGFloat OmiWindowInset = 8.0;
static const CGFloat OmiWindowTopInset = 12.0;
static const CGFloat OmiTrafficLightLeading = 16.0;
static const CGFloat OmiTrafficLightSpacing = 8.0;
static const CGFloat OmiTrafficLightChromeHeight = 52.0;

@interface OmiTitlebarPassthroughView : NSView
@end

@implementation OmiTitlebarPassthroughView

- (NSView *)hitTest:(NSPoint)point
{
  return nil;
}

@end

static void OmiSwizzleTitlebarHitTest(Class cls)
{
  static NSMutableSet<NSString *> *swizzled;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    swizzled = [NSMutableSet new];
  });
  if (cls == Nil) {
    return;
  }
  NSString *name = NSStringFromClass(cls);
  if ([swizzled containsObject:name]) {
    return;
  }
  [swizzled addObject:name];
  SEL selector = @selector(hitTest:);
  Method method = class_getInstanceMethod(cls, selector);
  if (method == NULL) {
    return;
  }
  NSView *(*original)(id, SEL, NSPoint) =
      (NSView * (*)(id, SEL, NSPoint)) method_getImplementation(method);
  IMP replacement = imp_implementationWithBlock(^NSView *(NSView *self, NSPoint point) {
    NSView *hit = original(self, selector, point);
    if (hit == nil) {
      return nil;
    }
    for (NSView *view = hit; view != nil; view = view.superview) {
      if ([view isKindOfClass:NSButton.class]) {
        return hit;
      }
      if (view == self) {
        break;
      }
    }
    return nil;
  });
  method_setImplementation(method, replacement);
}

static BOOL OmiViewBlocksWindowDrag(NSView *view)
{
  if ([view isKindOfClass:NSControl.class] || [view isKindOfClass:NSText.class] ||
      [view isKindOfClass:NSScrollView.class] || [view isKindOfClass:NSTextView.class]) {
    return YES;
  }
  if (!view.mouseDownCanMoveWindow) {
    return YES;
  }
  NSAccessibilityRole role = view.accessibilityRole;
  NSAccessibilitySubrole subrole = view.accessibilitySubrole;
  if ([role isEqualToString:NSAccessibilityButtonRole] ||
      [role isEqualToString:NSAccessibilityTextFieldRole] ||
      [role isEqualToString:NSAccessibilityTextAreaRole] ||
      [role isEqualToString:NSAccessibilityCheckBoxRole] ||
      [role isEqualToString:NSAccessibilityLinkRole] ||
      [role isEqualToString:NSAccessibilityPopUpButtonRole] ||
      [subrole isEqualToString:NSAccessibilitySearchFieldSubrole]) {
    return YES;
  }
  NSString *className = NSStringFromClass(view.class);
  if ([className containsString:@"RCTText"] || [className containsString:@"RCTUIText"] ||
      [className containsString:@"RCTScroll"]) {
    return YES;
  }
  return NO;
}

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
    OmiGlassPanelView *glass = [[OmiGlassPanelView alloc] initWithFrame:rootView.bounds];
    [glass setGlassCornerRadius:0];
    glass.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.omiWindowGlass = glass;
  }
  self.omiWindowGlass.frame = rootView.bounds;
  if (self.omiWindowGlass.superview != rootView) {
    [rootView addSubview:self.omiWindowGlass positioned:NSWindowBelow relativeTo:nil];
  }
}

- (void)hideOmiTitlebarMaterial:(NSWindow *)window
{
  NSButton *closeButton = [window standardWindowButton:NSWindowCloseButton];
  NSView *titlebar = closeButton.superview;
  for (NSView *view in titlebar.subviews) {
    if ([view isKindOfClass:NSVisualEffectView.class]) {
      view.hidden = YES;
    }
  }
  titlebar.wantsLayer = YES;
  titlebar.layer.backgroundColor = NSColor.clearColor.CGColor;
}

- (void)installOmiTitlebarAccessory:(NSWindow *)window
{
  if (self.omiTitlebarAccessory != nil) {
    return;
  }
  NSView *spacer = [[OmiTitlebarPassthroughView alloc]
      initWithFrame:NSMakeRect(0, 0, 0, OmiTrafficLightChromeHeight + OmiWindowTopInset)];
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
  window.toolbar = nil;
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
  [self hideOmiTitlebarMaterial:window];
  [self installOmiTitlebarClickThrough:window];
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
  NSView *frameView = window.contentView.superview ?: container;
  CGFloat buttonWidth = NSWidth(closeButton.frame);
  CGFloat buttonHeight = NSHeight(closeButton.frame);
  CGFloat yInFrame = NSHeight(frameView.bounds) - OmiWindowTopInset - OmiTrafficLightChromeHeight +
      floor((OmiTrafficLightChromeHeight - buttonHeight) / 2.0);
  CGFloat xInFrame = OmiWindowInset + OmiTrafficLightLeading;
  for (NSButton *button in @[ closeButton, miniaturizeButton, zoomButton ]) {
    NSPoint inFrame = NSMakePoint(xInFrame, yInFrame);
    NSPoint inContainer = [container convertPoint:inFrame fromView:frameView];
    NSRect frame = button.frame;
    frame.origin = inContainer;
    button.frame = frame;
    xInFrame += buttonWidth + OmiTrafficLightSpacing;
  }
}

- (void)installOmiTitlebarClickThrough:(NSWindow *)window
{
  NSButton *closeButton = [window standardWindowButton:NSWindowCloseButton];
  NSView *titlebar = closeButton.superview;
  if (titlebar == nil) {
    return;
  }
  OmiSwizzleTitlebarHitTest(titlebar.class);
  OmiSwizzleTitlebarHitTest(titlebar.superview.class);
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
    if (OmiViewBlocksWindowDrag(view)) {
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
