#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"
#import "OmiGlassPanelView.h"

#import <CoreGraphics/CoreGraphics.h>
#import <React/RCTBundleURLProvider.h>
#import <React/RCTDevLoadingViewSetEnabled.h>
#import <React/RCTUIKit.h>
#import <React/RCTViewManager.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>
#import <objc/runtime.h>
#import <stdio.h>

static const CGFloat OmiWindowInset = 12.0;
// Matches desktopOmnibarHeight in desktopChrome.ts: the top chrome row the
// titlebar accessory spacer and drag surface align to. v5 and v5.1 shells
// share it, and the virtual traffic lights (DesktopTrafficLights) center on
// it inside the React chrome.
static const CGFloat OmiChromeRowHeight = 44.0;
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

static BOOL OmiClassOwnsInstanceMethod(Class cls, SEL selector, Method *methodOut)
{
  unsigned int methodCount = 0;
  Method *methods = class_copyMethodList(cls, &methodCount);
  Method ownMethod = NULL;
  for (unsigned int index = 0; index < methodCount; index++) {
    if (method_getName(methods[index]) == selector) {
      ownMethod = methods[index];
      break;
    }
  }
  free(methods);
  if (methodOut != NULL) {
    *methodOut = ownMethod;
  }
  return ownMethod != NULL;
}

static BOOL OmiInstallClassLocalHitTestOverride(Class cls, IMP replacement, IMP *originalOut)
{
  SEL selector = @selector(hitTest:);
  Method method = class_getInstanceMethod(cls, selector);
  if (method == NULL) {
    return NO;
  }

  // If cls inherits hitTest:, method_setImplementation on this Method mutates
  // its superclass and changes hit testing for every view using that class.
  // Capture the inherited implementation before adding a class-local override.
  IMP original = method_getImplementation(method);
  const char *typeEncoding = method_getTypeEncoding(method);
  if (original == NULL || typeEncoding == NULL) {
    return NO;
  }
  if (originalOut != NULL) {
    *originalOut = original;
  }
  if (class_addMethod(cls, selector, replacement, typeEncoding)) {
    return YES;
  }

  // class_addMethod fails for a class-owned method; only then is it safe to
  // replace that method's implementation directly.
  Method ownMethod = NULL;
  if (!OmiClassOwnsInstanceMethod(cls, selector, &ownMethod)) {
    return NO;
  }
  if (originalOut != NULL) {
    *originalOut = method_getImplementation(ownMethod);
  }
  method_setImplementation(ownMethod, replacement);
  return YES;
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
  __block IMP original = NULL;
  // Dev-mode bundle reloads can transiently leave the view graph cyclic; a
  // cyclic hitTest walk overflows the stack and takes down the whole app.
  // A depth far above any legitimate React hierarchy bails out instead.
  // 96, not 512: each level costs ~7 native frames (hitTest + pointInside +
  // tracking-area cursorUpdate), so 512 levels exhausts the 8 MB main-thread
  // stack before this guard trips — the crash the guard exists to prevent.
  static thread_local NSUInteger omiHitTestDepth = 0;
  static BOOL omiHitTestGuardLogged = NO;
  IMP replacement = imp_implementationWithBlock(^NSView *(NSView *self, NSPoint point) {
    if (omiHitTestDepth > 96) {
      if (!omiHitTestGuardLogged) {
        omiHitTestGuardLogged = YES;
        NSString *note = [NSString stringWithFormat:
            @"%@ [OmiUI] hitTest depth guard tripped class=%@ — content input dead\n",
            NSDate.date, NSStringFromClass(self.class)];
        FILE *log = fopen("/tmp/omi-auth-debug.log", "a");
        if (log != NULL) { fwrite(note.UTF8String, 1, strlen(note.UTF8String), log); fclose(log); }
      }
      return nil;
    }
    omiHitTestDepth += 1;
    NSView *hit = ((NSView *(*)(id, SEL, NSPoint))original)(self, selector, point);
    omiHitTestDepth -= 1;
    return hit;
  });
  if (!OmiInstallClassLocalHitTestOverride(cls, replacement, &original)) {
    [swizzled removeObject:name];
  }
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
  __block IMP original = NULL;
  IMP replacement = imp_implementationWithBlock(^NSView *(NSView *self, NSPoint point) {
    NSView *hit = ((NSView *(*)(id, SEL, NSPoint))original)(self, selector, point);
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
  if (!OmiInstallClassLocalHitTestOverride(cls, replacement, &original)) {
    [swizzled removeObject:name];
  }
}

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  // RN's dev loading indicator is a borderless helper window that flashes
  // over the custom desktop chrome on every Metro load/reload; the app has
  // its own launch surface, so keep that overlay off entirely.
  RCTDevLoadingViewSetEnabled(NO);
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
  __weak AppDelegate *weakSelfForClose = self;
  self.omiWindowCloseObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:NSWindowWillCloseNotification
                                                       object:self.window
                                                        queue:NSOperationQueue.mainQueue
                                                   usingBlock:^(__unused NSNotification *note) {
    // The content hierarchy goes away with the window; later update or
    // workspace notifications must not reach dressOmiWindow anymore.
    weakSelfForClose.omiWindowToreDown = YES;
    if (weakSelfForClose.omiWindowUpdateObserver != nil) {
      [NSNotificationCenter.defaultCenter removeObserver:weakSelfForClose.omiWindowUpdateObserver];
      weakSelfForClose.omiWindowUpdateObserver = nil;
    }
  }];
  [self installDesktopSearchCommand];
  self.omiAppearanceObserver =
      [NSNotificationCenter.defaultCenter addObserverForName:OmiDesktopAppearanceDidChangeNotification
          object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) {
    [weakSelf dressOmiWindow];
  }];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender
{
  // Single-window app: closing the window (native menu, Cmd-W, or the
  // virtual traffic light's performClose:) should end the process — a
  // windowless RnRuntime has no surface left to reopen.
  return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification
{
  self.omiWindowToreDown = YES;
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
  if (self.omiWindowCloseObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiWindowCloseObserver];
    self.omiWindowCloseObserver = nil;
  }
  if (self.omiAppearanceObserver != nil) {
    [NSNotificationCenter.defaultCenter removeObserver:self.omiAppearanceObserver];
    self.omiAppearanceObserver = nil;
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
    [rootView addSubview:self.omiWindowGlass
              positioned:NSWindowBelow
              relativeTo:nil];
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
  // Window-update and workspace notifications can arrive after AppKit has
  // begun releasing the window's content hierarchy (quit, last-window close).
  // Touching the half-torn-down view tree segfaults, so stop early.
  if (self.omiWindowToreDown) {
    return;
  }
  NSWindow *window = self.window;
  if (window == nil || window.contentViewController == nil ||
      window.contentViewController.view == nil) {
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
  // Window dragging is the native movableByWindowBackground path: RN
  // Pressables set mouseDownCanMoveWindow=false on their hosts, so buttons
  // stay clickable while bare surface areas drag the window. The previous
  // custom event monitor misclassified RN View children (their React default
  // is mouseDownCanMoveWindow=true) as drag ground and swallowed clicks on
  // header button padding.
  window.movableByWindowBackground = YES;
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
  // Native traffic lights stay hidden: the chrome row draws its own virtual
  // lights (DesktopTrafficLights) at the exact spacer geometry, so AppKit's
  // hover/hit layout for the real buttons can never desync from ours again.
  [window standardWindowButton:NSWindowCloseButton].hidden = YES;
  [window standardWindowButton:NSWindowMiniaturizeButton].hidden = YES;
  [window standardWindowButton:NSWindowZoomButton].hidden = YES;
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
