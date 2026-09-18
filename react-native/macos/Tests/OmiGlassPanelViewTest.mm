#import "../RnRuntime-macOS/OmiGlassPanelView.mm"
#import <objc/runtime.h>
#include <cassert>

@implementation RCTView
@end
@implementation RCTViewManager
@end

static BOOL reducedTransparency = NO;
static BOOL testReducedTransparency(id object, SEL selector) { return reducedTransparency; }

int main(void) {
  @autoreleasepool {
    [NSApplication sharedApplication];
    // Exercise the newer-OS branch even on older CI Macs. The previous code
    // would allocate this empty floating-glass surface behind React content.
    if (NSClassFromString(@"NSGlassEffectView") == Nil) {
      objc_registerClassPair(objc_allocateClassPair(NSView.class, "NSGlassEffectView", 0));
    }
    Method preference = class_getInstanceMethod(NSWorkspace.class,
        @selector(accessibilityDisplayShouldReduceTransparency));
    IMP original = method_setImplementation(preference, (IMP)testReducedTransparency);
    @try {
      OmiGlassPanelView *panel = [[OmiGlassPanelView alloc] initWithFrame:NSZeroRect];
      NSView *host = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 900, 700)];
      [host addSubview:panel];
      assert(panel.subviews.count == 2);
      assert([panel.material isKindOfClass:NSVisualEffectView.class]);
      assert(panel.material.blendingMode == NSVisualEffectBlendingModeBehindWindow);
      assert(panel.material.state == NSVisualEffectStateActive);
      assert(!panel.material.hidden && panel.fallback.hidden);
      for (NSView *child in panel.subviews) {
        assert(![child isKindOfClass:NSClassFromString(@"NSGlassEffectView")]);
      }

      // App -> welcome -> permission guide -> welcome -> app, including
      // detach/reattach. No decoration may retain a previous capsule frame.
      for (NSValue *size in @[
          [NSValue valueWithSize:NSMakeSize(900, 700)],
          [NSValue valueWithSize:NSMakeSize(720, 700)],
          [NSValue valueWithSize:NSMakeSize(380, 480)],
          [NSValue valueWithSize:NSMakeSize(720, 700)],
          [NSValue valueWithSize:NSMakeSize(1040, 780)]]) {
        [panel removeFromSuperview];
        [host addSubview:panel];
        panel.frame = NSMakeRect(0, 0, size.sizeValue.width, size.sizeValue.height);
        [panel layout];
        assert(NSEqualRects(panel.material.frame, panel.bounds));
        assert(NSEqualRects(panel.fallback.frame, panel.bounds));
        assert(CGRectEqualToRect(panel.scrim.frame, NSRectToCGRect(panel.bounds)));
        assert(panel.sheen.frame.size.width == size.sizeValue.width);
        assert(panel.scrim.animationKeys.count == 0 && panel.sheen.animationKeys.count == 0);
        assert(panel.subviews.count == 2);
        assert([panel hitTest:NSMakePoint(10, 10)] == nil);
      }
      reducedTransparency = YES;
      [panel applyAccessibilityAppearance];
      assert(panel.material.hidden && !panel.fallback.hidden && panel.sheen.hidden);
      reducedTransparency = NO;
      [panel applyAccessibilityAppearance];
      assert(!panel.material.hidden && panel.fallback.hidden && !panel.sheen.hidden);
      puts("Window backdrop: no empty floating glass; bounds, remount, and accessibility tests passed");
    } @finally {
      method_setImplementation(preference, original);
    }
  }
}
