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
@property (nonatomic, strong) NSView *contentHost;
@property (nonatomic, strong) NSView *finish;
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
  self.clipsToBounds = YES;
  self.layer.masksToBounds = YES;
  self.appearance = OmiInkGlassAppearance();
  self.layer.borderWidth = 1;

  self.contentHost = [[NSView alloc] initWithFrame:self.bounds];
  self.contentHost.wantsLayer = YES;
  self.contentHost.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  self.finish = [[NSView alloc] initWithFrame:self.bounds];
  self.finish.wantsLayer = YES;
  self.finish.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  [self.contentHost addSubview:self.finish];

  self.liquidGlass = OmiMakeLiquidGlass(self.bounds, defaultCornerRadius);
  if (self.liquidGlass != nil) {
    [self addSubview:self.liquidGlass];
  }
  if (self.liquidGlass == nil) {
    self.material = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
    self.material.appearance = OmiInkGlassAppearance();
    self.material.material = NSVisualEffectMaterialHUDWindow;
    self.material.blendingMode = NSVisualEffectBlendingModeBehindWindow;
    self.material.state = NSVisualEffectStateActive;
    self.material.wantsLayer = YES;
    self.material.layer.masksToBounds = YES;
    [self addSubview:self.material];
  }

  self.fallback = [[NSView alloc] initWithFrame:self.bounds];
  self.fallback.wantsLayer = YES;
  self.fallback.layer.masksToBounds = YES;
  [self addSubview:self.fallback];

  self.scrim = [CALayer layer];
  [self.finish.layer addSublayer:self.scrim];
  self.sheen = [CALayer layer];
  [self.finish.layer addSublayer:self.sheen];

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
  self.finish.layer.cornerRadius = _glassCornerRadius;
  self.finish.layer.cornerCurve = kCACornerCurveContinuous;
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
  NSPoint local = [self convertPoint:point fromView:self.superview];
  if (self.isHidden || ![self mouse:local inRect:self.bounds] || self.contentHost == nil) {
    return nil;
  }
  NSView *hostSuperview = self.contentHost.superview;
  if (hostSuperview == nil) {
    return nil;
  }
  NSView *hit = [self.contentHost hitTest:[hostSuperview convertPoint:local fromView:self]];
  if (hit == nil || hit == self.contentHost || hit == self.finish) {
    return nil;
  }
  return hit;
}

- (void)layout
{
  [super layout];
  self.liquidGlass.frame = self.bounds;
  self.material.frame = self.bounds;
  self.fallback.frame = self.bounds;
  if (self.contentHost.superview == self) {
    self.contentHost.frame = self.bounds;
  } else if (self.contentHost.superview != nil) {
    self.contentHost.frame = self.contentHost.superview.bounds;
  }
  self.finish.frame = self.contentHost.bounds;
  self.scrim.frame = self.finish.bounds;
  self.sheen.frame = NSMakeRect(0, NSMaxY(self.bounds) - OmiGlassSheenHeight, NSWidth(self.bounds),
      OmiGlassSheenHeight);
}

- (void)omiAttachContentHost
{
  BOOL reduceTransparency = NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceTransparency;
  BOOL useGlassContent = self.liquidGlass != nil && !self.liquidGlass.hidden && !reduceTransparency &&
      [self.liquidGlass respondsToSelector:@selector(setContentView:)];
  if (useGlassContent) {
    ((void (*)(id, SEL, id))objc_msgSend)(
        self.liquidGlass, @selector(setContentView:), self.contentHost);
    return;
  }
  if ([self.liquidGlass respondsToSelector:@selector(setContentView:)]) {
    id current = ((id (*)(id, SEL))objc_msgSend)(self.liquidGlass, @selector(contentView));
    if (current == self.contentHost) {
      ((void (*)(id, SEL, id))objc_msgSend)(self.liquidGlass, @selector(setContentView:), nil);
    }
  }
  if (self.contentHost.superview != self) {
    [self addSubview:self.contentHost];
  }
}

- (void)insertReactSubview:(RCTUIView *)subview atIndex:(NSInteger)atIndex
{
  [super insertReactSubview:subview atIndex:atIndex];
  NSArray<NSView *> *siblings = self.contentHost.subviews;
  NSInteger hostIndex = atIndex + 1;
  if (hostIndex >= 0 && hostIndex < (NSInteger)siblings.count) {
    [self.contentHost addSubview:subview positioned:NSWindowBelow relativeTo:siblings[hostIndex]];
    return;
  }
  [self.contentHost addSubview:subview];
}

- (void)removeReactSubview:(RCTUIView *)subview
{
  [super removeReactSubview:subview];
}

- (void)didUpdateReactSubviews
{
}

- (void)applyAccessibilityAppearance
{
  BOOL reduceTransparency = NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceTransparency;
  BOOL hasLiquid = self.liquidGlass != nil;
  self.liquidGlass.hidden = reduceTransparency || !hasLiquid;
  if (self.material != nil) {
    self.material.hidden = reduceTransparency;
  }
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
  [self omiAttachContentHost];
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
