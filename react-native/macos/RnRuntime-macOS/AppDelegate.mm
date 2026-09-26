#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"
#import "OmiGlassPanelView.h"

#import <CoreGraphics/CoreGraphics.h>
#import <React/RCTBundleURLProvider.h>
#import <React/RCTUIKit.h>
#import <React/RCTViewManager.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>
#import <objc/runtime.h>

static const CGFloat OmiWindowInset = 12.0;
static const CGFloat OmiTrafficLightSpacing = 8.0;
static const CGFloat OmiChromeRowHeight = 52.0;
static NSString *const OmiWindowPresentationChanged = @"OmiWindowPresentationChanged";

// An inert React marker changes the existing window, never reparents React
// children into another surface. Removing the screen restores the app window.
@interface OmiDesktopWindowView : RCTView
@property (nonatomic, copy) NSString *presentation;
@property (nonatomic, weak) NSWindow *owningWindow;
@end

@implementation OmiDesktopWindowView
- (void)setPresentation:(NSString *)presentation
{
  _presentation = [presentation copy];
  if (self.window != nil) {
    [NSNotificationCenter.defaultCenter postNotificationName:OmiWindowPresentationChanged
        object:self.window userInfo:@{@"presentation": _presentation ?: @"app"}];
  }
}
- (void)viewDidMoveToWindow
{
  [super viewDidMoveToWindow];
  if (self.owningWindow != nil && self.owningWindow != self.window) {
    [NSNotificationCenter.defaultCenter postNotificationName:OmiWindowPresentationChanged
        object:self.owningWindow userInfo:@{@"presentation": @"app"}];
  }
  self.owningWindow = self.window;
  [self setPresentation:self.presentation];
}
@end

@interface OmiDesktopWindowManager : RCTViewManager
@end
@implementation OmiDesktopWindowManager
RCT_EXPORT_MODULE(OmiDesktopWindow)
RCT_EXPORT_VIEW_PROPERTY(presentation, NSString)
- (NSView *)view { return [[OmiDesktopWindowView alloc] initWithFrame:NSZeroRect]; }
+ (BOOL)requiresMainQueueSetup { return YES; }
@end

@interface OmiTitlebarPassthroughView : NSView
@end

@implementation OmiTitlebarPassthroughView

- (NSView *)hitTest:(NSPoint)point
{
  return nil;
}

@end

static NSView *OmiTrafficLightHit(NSView *fromView, NSPoint point)
{
  NSWindow *window = fromView.window;
  if (window == nil) {
    return nil;
  }
  for (NSNumber *kind in @[
         @(NSWindowCloseButton), @(NSWindowMiniaturizeButton), @(NSWindowZoomButton)
       ]) {
    NSButton *button = [window standardWindowButton:(NSWindowButton)kind.unsignedIntegerValue];
    if (button == nil || button.hidden) {
      continue;
    }
    NSPoint inButton = [fromView convertPoint:point toView:button];
    if (NSMouseInRect(inButton, button.bounds, button.flipped)) {
      NSView *hit = [button hitTest:inButton];
      return hit != nil ? hit : button;
    }
  }
  return nil;
}

static void OmiSwizzleContentHitTest(NSView *contentView)
{
  static NSMutableSet<NSString *> *swizzled;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    swizzled = [NSMutableSet new];
  });
  Class cls = contentView.class;
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
    NSView *light = OmiTrafficLightHit(self, point);
    if (light != nil) {
      return light;
    }
    return original(self, selector, point);
  });
  method_setImplementation(method, replacement);
}

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

  self.omiWindowFrames = [NSMutableDictionary new];
  self.omiWindowPresentation = @"app";
  __weak AppDelegate *weakSelf = self;
  self.omiWindowPresentationObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:OmiWindowPresentationChanged
          object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
    if (note.object == weakSelf.window) {
      [weakSelf applyOmiWindowPresentation:note.userInfo[@"presentation"]];
    }
  }];
  self.omiWorkspaceObserver =
      [NSWorkspace.sharedWorkspace.notificationCenter
          addObserverForName:NSWorkspaceDidActivateApplicationNotification
          object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
    [weakSelf dressOmiWindow];
    if ([weakSelf.omiWindowPresentation isEqualToString:@"permission-guide"] &&
        [NSWorkspace.sharedWorkspace.frontmostApplication.bundleIdentifier
            isEqualToString:@"com.apple.systempreferences"]) {
      [weakSelf positionOmiPermissionGuide];
    }
  }];
  [super applicationDidFinishLaunching:notification];
  [self dressOmiWindow];
  self.omiWindowUpdateObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:NSWindowDidUpdateNotification
                                                       object:self.window
                                                        queue:NSOperationQueue.mainQueue
                                                   usingBlock:^(__unused NSNotification *note) {
    [weakSelf dressOmiWindow];
  }];
  [self installDesktopSearchCommand];
  [self installOmiWindowDragMonitor];
  self.omiAppearanceObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:OmiDesktopAppearanceDidChangeNotification
          object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
    [weakSelf dressOmiWindow];
  }];
}

- (void)applicationWillTerminate:(NSNotification *)notification
{
  [self.omiGuidePlacementTimer invalidate];
  if (self.omiWindowPresentationObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiWindowPresentationObserver];
  }
  if (self.omiWorkspaceObserver != nil) {
    [NSWorkspace.sharedWorkspace.notificationCenter removeObserver:self.omiWorkspaceObserver];
  }
  if (self.omiWindowUpdateObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiWindowUpdateObserver];
    self.omiWindowUpdateObserver = nil;
  }
  if (self.omiAppearanceObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiAppearanceObserver];
    self.omiAppearanceObserver = nil;
  }
  if (self.omiWindowDragMonitor != nil) {
    [NSEvent removeMonitor:self.omiWindowDragMonitor];
    self.omiWindowDragMonitor = nil;
  }
  if (self.omiTitlebarLayoutObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiTitlebarLayoutObserver];
    self.omiTitlebarLayoutObserver = nil;
  }
  [super applicationWillTerminate:notification];
}

- (void)applyOmiWindowPresentation:(NSString *)presentation
{
  if (![presentation isEqualToString:@"app"] &&
      ![presentation isEqualToString:@"onboarding"] &&
      ![presentation isEqualToString:@"permission-guide"]) {
    return;
  }
  if ([self.omiWindowPresentation isEqualToString:presentation] || self.window == nil) {
    return;
  }
  NSString *previous = self.omiWindowPresentation;
  self.omiWindowFrames[previous] = [NSValue valueWithRect:self.window.frame];
  self.omiWindowPresentation = presentation;
  [self.omiGuidePlacementTimer invalidate];
  self.omiGuidePlacementTimer = nil;
  self.omiGuideFitsBesideSettings = NO;
  [self dressOmiWindow];
  NSValue *saved = self.omiWindowFrames[presentation];
  if (saved != nil) {
    [self.window setFrame:saved.rectValue display:YES];
  } else {
    [self.window setContentSize:[presentation isEqualToString:@"permission-guide"]
        ? NSMakeSize(380, 480) : NSMakeSize(720, 700)];
    [self.window center];
  }
  // Grant polling only updates React content. Only an explicit return changes
  // out of guide mode and brings Omi back; never steal focus from a TCC prompt.
  if ([presentation isEqualToString:@"permission-guide"]) {
    [self positionOmiPermissionGuide];
    __weak AppDelegate *weakSelf = self;
    self.omiGuidePlacementTimer = [NSTimer scheduledTimerWithTimeInterval:0.5 repeats:YES
        block:^(__unused NSTimer *timer) {
      if ([NSWorkspace.sharedWorkspace.frontmostApplication.bundleIdentifier
          isEqualToString:@"com.apple.systempreferences"] && !weakSelf.window.miniaturized) {
        [weakSelf positionOmiPermissionGuide];
      }
    }];
  } else if ([previous isEqualToString:@"permission-guide"]) {
    [NSApp activateIgnoringOtherApps:YES];
    [self.window makeKeyAndOrderFront:nil];
  }
}

- (void)positionOmiPermissionGuide
{
  NSWindow *window = self.window;
  NSScreen *screen = window.screen ?: NSScreen.mainScreen;
  NSRect settingsFrame = NSZeroRect;
  NSArray *windows = CFBridgingRelease(CGWindowListCopyWindowInfo(
      kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID));
  // Bounds and PID only: no screenshot, OCR, window titles, or Accessibility
  // permission. This is words-only guidance, never an arrow to an unmeasured switch.
  for (NSRunningApplication *app in [NSRunningApplication
      runningApplicationsWithBundleIdentifier:@"com.apple.systempreferences"]) {
    for (NSDictionary *info in windows) {
      if ([info[(id)kCGWindowOwnerPID] intValue] != app.processIdentifier ||
          [info[(id)kCGWindowLayer] intValue] != 0) {
        continue;
      }
      CGRect bounds;
      if (!CGRectMakeWithDictionaryRepresentation((__bridge CFDictionaryRef)
              info[(id)kCGWindowBounds], &bounds) || bounds.size.width < 300) {
        continue;
      }
      // Quartz is top-left relative to the primary display; AppKit is bottom-left.
      CGFloat primaryTop = NSMaxY(NSScreen.screens.firstObject.frame);
      settingsFrame = NSMakeRect(bounds.origin.x, primaryTop - CGRectGetMaxY(bounds),
          bounds.size.width, bounds.size.height);
      for (NSScreen *candidate in NSScreen.screens) {
        if (NSPointInRect(NSMakePoint(NSMidX(settingsFrame), NSMidY(settingsFrame)), candidate.frame)) {
          screen = candidate;
          break;
        }
      }
      break;
    }
  }
  if (screen == nil) { return; }
  NSRect visible = NSInsetRect(screen.visibleFrame, 16, 16);
  NSRect frame = window.frame;
  frame.size.width = MIN(frame.size.width, NSWidth(visible));
  frame.size.height = MIN(frame.size.height, NSHeight(visible));
  CGFloat right = NSMaxX(settingsFrame) + 16;
  CGFloat left = NSMinX(settingsFrame) - NSWidth(frame) - 16;
  BOOL fitsRight = right >= NSMinX(visible) && right + NSWidth(frame) <= NSMaxX(visible);
  BOOL fitsLeft = left >= NSMinX(visible) && left + NSWidth(frame) <= NSMaxX(visible);
  BOOL beside = !NSIsEmptyRect(settingsFrame) && (fitsRight || fitsLeft);
  self.omiGuideFitsBesideSettings = beside;
  if (beside) {
    frame.origin.x = fitsRight ? right : left;
    frame.origin.y = NSMidY(settingsFrame) - NSHeight(frame) / 2;
    frame.origin.y = MAX(NSMinY(visible), MIN(frame.origin.y, NSMaxY(visible) - NSHeight(frame)));
  } else {
    frame.origin = NSMakePoint(NSMaxX(visible) - NSWidth(frame), NSMinY(visible));
  }
  if (!NSEqualRects(window.frame, frame)) {
    [window setFrame:frame display:YES];
  }
  // If there is no room beside Settings, leave the guide behind it rather than
  // cover its controls. The user can return to Omi from the Dock or Cmd-Tab.
  if ([NSWorkspace.sharedWorkspace.frontmostApplication.bundleIdentifier
      isEqualToString:@"com.apple.systempreferences"]) {
    window.level = beside ? NSFloatingWindowLevel : NSNormalWindowLevel;
    if (!beside) {
      [window orderBack:nil];
    }
  }
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
      initWithFrame:NSMakeRect(0, 0, 0, OmiChromeRowHeight + OmiWindowInset)];
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

  window.appearance = [NSAppearance appearanceNamed:OmiPreferredDesktopAppearance()];
  window.opaque = NO;
  window.backgroundColor = NSColor.clearColor;
  RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;
  rootView.appearance = [NSAppearance appearanceNamed:OmiPreferredDesktopAppearance()];
  rootView.backgroundColor = NSColor.clearColor;
  window.hasShadow = YES;
  window.styleMask = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
      NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable |
      NSWindowStyleMaskFullSizeContentView;
  window.titlebarAppearsTransparent = YES;
  window.titleVisibility = NSWindowTitleHidden;
  window.title = @"";
  window.toolbar = nil;
  window.titlebarSeparatorStyle = NSTitlebarSeparatorStyleNone;
  window.movableByWindowBackground = NO;
  BOOL guide = [self.omiWindowPresentation isEqualToString:@"permission-guide"];
  NSRunningApplication *front = NSWorkspace.sharedWorkspace.frontmostApplication;
  NSWindowLevel level = guide && (front.processIdentifier == NSProcessInfo.processInfo.processIdentifier ||
      (self.omiGuideFitsBesideSettings &&
          [front.bundleIdentifier isEqualToString:@"com.apple.systempreferences"]))
      ? NSFloatingWindowLevel : NSNormalWindowLevel;
  if (window.level != level) {
    window.level = level;
  }
  window.hidesOnDeactivate = NO;
  window.contentMinSize = guide ? NSMakeSize(340, 420) :
      [self.omiWindowPresentation isEqualToString:@"onboarding"] ?
          NSMakeSize(640, 620) : NSMakeSize(800, 680);
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
  OmiSwizzleContentHitTest(window.contentView);
  [window standardWindowButton:NSWindowCloseButton].hidden = NO;
  [window standardWindowButton:NSWindowMiniaturizeButton].hidden = NO;
  [window standardWindowButton:NSWindowZoomButton].hidden = NO;
  [self positionOmiTrafficLights];
  [self observeOmiTitlebarLayout];
}

// AppKit re-centers the traffic lights inside the accessory-grown titlebar
// whenever it relays out the titlebar container (accessory install, window
// resize, appearance change). Re-apply our row-aligned frames whenever the
// titlebar container moves or resizes, and once on the next layout pass.
- (void)observeOmiTitlebarLayout
{
  if (self.omiTitlebarLayoutObserver != nil) {
    return;
  }
  NSButton *closeButton = [self.window standardWindowButton:NSWindowCloseButton];
  NSView *titlebar = closeButton.superview;
  if (titlebar == nil) {
    return;
  }
  titlebar.postsFrameChangedNotifications = YES;
  titlebar.superview.postsFrameChangedNotifications = YES;
  __weak AppDelegate *weakSelf = self;
  self.omiTitlebarLayoutObserver = [[NSNotificationCenter defaultCenter]
      addObserverForName:NSViewFrameDidChangeNotification
                  object:titlebar
                   queue:nil
              usingBlock:^(NSNotification *) {
                [weakSelf positionOmiTrafficLights];
              }];
  dispatch_async(dispatch_get_main_queue(), ^{
    [weakSelf positionOmiTrafficLights];
  });
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
  // Center the lights on the React chrome row: the row starts at the even
  // window inset and is OmiChromeRowHeight tall, so its center sits
  // OmiWindowInset + OmiChromeRowHeight / 2 below the top of the frame view.
  CGFloat yInFrame = NSHeight(frameView.bounds) - OmiWindowInset - OmiChromeRowHeight +
      floor((OmiChromeRowHeight - buttonHeight) / 2.0);
  CGFloat xInFrame = OmiWindowInset;
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
