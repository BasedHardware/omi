#import "OmiGlassPanelView.h"

#import <React/RCTViewManager.h>
#import <objc/message.h>
#import <objc/runtime.h>

static const CGFloat defaultCornerRadius = 22.0;
static const CGFloat OmiGlassScrimAlpha = 0.46;
static const CGFloat OmiGlassEdgeAlpha = 0.06;
static const CGFloat OmiGlassSheenAlpha = 0.5;
static const CGFloat OmiGlassSheenHeight = 1.0;

static NSAppearance *OmiInkGlassAppearance(void)
{
  return [NSAppearance appearanceNamed:NSAppearanceNameAqua];
}

static NSView *OmiMakeLiquidGlass(NSRect frame, CGFloat radius)
{
  Class glassClass = NSClassFromString(@"NSGlassEffectView");
  if (glassClass == Nil) {
    return nil;
  }
  NSView *glass = [[glassClass alloc] initWithFrame:frame];
  glass.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  if ([glass respondsToSelector:@selector(setCornerRadius:)]) {
    ((void (*)(id, SEL, CGFloat))objc_msgSend)(glass, @selector(setCornerRadius:), radius);
  }
  if ([glass respondsToSelector:@selector(setStyle:)]) {
    ((void (*)(id, SEL, NSInteger))objc_msgSend)(glass, @selector(setStyle:), 0);
  }
  if ([glass respondsToSelector:@selector(setTintColor:)]) {
    ((void (*)(id, SEL, id))objc_msgSend)(
        glass, @selector(setTintColor:), [NSColor colorWithCalibratedWhite:1.0 alpha:OmiGlassScrimAlpha]);
  }
  return glass;
}

@interface OmiGlassPanelView ()

{
  CGFloat _glassCornerRadius;
}

@property (nonatomic, strong) NSView *liquidGlass;
@property (nonatomic, strong) NSVisualEffectView *material;
@property (nonatomic, strong) NSView *fallback;
@property (nonatomic, strong) CALayer *scrim;
@property (nonatomic, strong) CALayer *sheen;
@property (nonatomic, strong, nullable) id accessibilityObserver;

@end

@implementation OmiGlassPanelView

- (instancetype)initWithFrame:(NSRect)frameRect
{
  self = [super initWithFrame:frameRect];
  if (self == nil) {
    return nil;
  }

  self.wantsLayer = YES;
  self.appearance = OmiInkGlassAppearance();
  self.layer.borderWidth = 1;

  self.liquidGlass = OmiMakeLiquidGlass(self.bounds, defaultCornerRadius);
  if (self.liquidGlass != nil) {
    [self addSubview:self.liquidGlass];
  }

  self.material = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
  self.material.appearance = OmiInkGlassAppearance();
  self.material.material = NSVisualEffectMaterialHUDWindow;
  self.material.blendingMode = NSVisualEffectBlendingModeBehindWindow;
  self.material.state = NSVisualEffectStateActive;
  self.material.wantsLayer = YES;
  self.material.layer.masksToBounds = YES;
  [self addSubview:self.material];

  self.fallback = [[NSView alloc] initWithFrame:self.bounds];
  self.fallback.wantsLayer = YES;
  self.fallback.layer.masksToBounds = YES;
  [self addSubview:self.fallback];

  self.scrim = [CALayer layer];
  [self.layer addSublayer:self.scrim];
  self.sheen = [CALayer layer];
  [self.layer addSublayer:self.sheen];

  __weak OmiGlassPanelView *weakSelf = self;
  self.accessibilityObserver =
      [NSWorkspace.sharedWorkspace.notificationCenter
          addObserverForName:NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification
                      object:nil
                       queue:NSOperationQueue.mainQueue
                   usingBlock:^(__unused NSNotification *note) {
    [weakSelf applyAccessibilityAppearance];
  }];
  self.glassCornerRadius = defaultCornerRadius;
  [self applyAccessibilityAppearance];
  return self;
}

- (void)dealloc
{
  if (self.accessibilityObserver != nil) {
    [NSWorkspace.sharedWorkspace.notificationCenter removeObserver:self.accessibilityObserver];
  }
}

- (void)setGlassCornerRadius:(CGFloat)glassCornerRadius
{
  _glassCornerRadius = glassCornerRadius;
  self.layer.cornerRadius = _glassCornerRadius;
  self.layer.cornerCurve = kCACornerCurveContinuous;
  self.material.layer.cornerRadius = _glassCornerRadius;
  self.material.layer.cornerCurve = kCACornerCurveContinuous;
  self.fallback.layer.cornerRadius = _glassCornerRadius;
  self.fallback.layer.cornerCurve = kCACornerCurveContinuous;
  self.scrim.cornerRadius = _glassCornerRadius;
  self.scrim.cornerCurve = kCACornerCurveContinuous;
  if (self.liquidGlass != nil && [self.liquidGlass respondsToSelector:@selector(setCornerRadius:)]) {
    ((void (*)(id, SEL, CGFloat))objc_msgSend)(
        self.liquidGlass, @selector(setCornerRadius:), _glassCornerRadius);
  }
}

- (BOOL)acceptsFirstMouse:(NSEvent *)event
{
  return NO;
}

- (NSView *)hitTest:(NSPoint)point
{
  return nil;
}

- (void)layout
{
  [super layout];
  self.liquidGlass.frame = self.bounds;
  self.material.frame = self.bounds;
  self.fallback.frame = self.bounds;
  self.scrim.frame = self.bounds;
  self.sheen.frame = NSMakeRect(0, NSMaxY(self.bounds) - OmiGlassSheenHeight, NSWidth(self.bounds),
      OmiGlassSheenHeight);
}

- (void)applyAccessibilityAppearance
{
  BOOL reduceTransparency = NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceTransparency;
  BOOL hasLiquid = self.liquidGlass != nil;
  self.liquidGlass.hidden = reduceTransparency || !hasLiquid;
  self.material.hidden = reduceTransparency || hasLiquid;
  self.fallback.hidden = !reduceTransparency;
  self.appearance = OmiInkGlassAppearance();
  [self.appearance performAsCurrentDrawingAppearance:^{
    self.fallback.layer.backgroundColor = NSColor.controlBackgroundColor.CGColor;
    CGFloat alpha = reduceTransparency ? 1.0 : OmiGlassScrimAlpha;
    self.scrim.backgroundColor = [NSColor.controlBackgroundColor colorWithAlphaComponent:alpha].CGColor;
    self.sheen.hidden = reduceTransparency;
    self.sheen.backgroundColor = [NSColor.whiteColor colorWithAlphaComponent:OmiGlassSheenAlpha].CGColor;
    self.layer.borderColor = [NSColor.labelColor colorWithAlphaComponent:OmiGlassEdgeAlpha].CGColor;
  }];
}

@end

@interface OmiGlassPanelManager : RCTViewManager

@end

@implementation OmiGlassPanelManager

RCT_EXPORT_MODULE(OmiGlassPanel)

RCT_EXPORT_VIEW_PROPERTY(glassCornerRadius, CGFloat)

- (NSView *)view
{
  return [[OmiGlassPanelView alloc] initWithFrame:NSZeroRect];
}

+ (BOOL)requiresMainQueueSetup
{
  return YES;
}

@end
