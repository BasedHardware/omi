#import "OmiGlassPanelView.h"

#import <React/RCTViewManager.h>

static const CGFloat defaultCornerRadius = 22.0;
static const CGFloat OmiGlassScrimAlpha = 0.46;
static const CGFloat OmiGlassEdgeAlpha = 0.06;
static const CGFloat OmiGlassSheenAlpha = 0.5;
static const CGFloat OmiGlassSheenHeight = 1.0;

static NSAppearance *OmiInkGlassAppearance(void)
{
  return [NSAppearance appearanceNamed:NSAppearanceNameAqua];
}

@interface OmiGlassPanelView ()

{
  CGFloat _glassCornerRadius;
}

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

  self.material = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
  self.material.appearance = OmiInkGlassAppearance();
  self.material.material = NSVisualEffectMaterialHUDWindow;
  self.material.blendingMode = NSVisualEffectBlendingModeBehindWindow;
  self.material.state = NSVisualEffectStateActive;
  self.material.wantsLayer = YES;
  self.material.layer.masksToBounds = YES;
  self.material.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  [self addSubview:self.material];

  self.fallback = [[NSView alloc] initWithFrame:self.bounds];
  self.fallback.wantsLayer = YES;
  self.fallback.layer.masksToBounds = YES;
  self.fallback.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  [self addSubview:self.fallback];

  self.finish = [[NSView alloc] initWithFrame:self.bounds];
  self.finish.wantsLayer = YES;
  self.finish.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  [self addSubview:self.finish];

  self.contentHost = [[NSView alloc] initWithFrame:self.bounds];
  self.contentHost.wantsLayer = YES;
  self.contentHost.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  [self addSubview:self.contentHost];

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
  self.material.frame = self.bounds;
  self.fallback.frame = self.bounds;
  self.finish.frame = self.bounds;
  if (self.contentHost.superview != self) {
    [self omiAttachContentHost];
  }
  self.contentHost.frame = self.bounds;
  self.scrim.frame = self.finish.bounds;
  self.sheen.frame = NSMakeRect(0, NSMaxY(self.bounds) - OmiGlassSheenHeight, NSWidth(self.bounds),
      OmiGlassSheenHeight);
}

- (void)omiAttachContentHost
{
  if (self.contentHost.superview != nil && self.contentHost.superview != self) {
    [self.contentHost removeFromSuperview];
  }
  if (self.contentHost.superview != self) {
    [self addSubview:self.contentHost];
  }
}

- (void)insertReactSubview:(RCTUIView *)subview atIndex:(NSInteger)atIndex
{
  [super insertReactSubview:subview atIndex:atIndex];
  if (self.contentHost.superview != self) {
    [self omiAttachContentHost];
  }
  NSArray<NSView *> *siblings = self.contentHost.subviews;
  if (atIndex >= 0 && atIndex < (NSInteger)siblings.count) {
    [self.contentHost addSubview:subview positioned:NSWindowBelow relativeTo:siblings[atIndex]];
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
  self.material.hidden = reduceTransparency;
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
