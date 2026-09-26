#import "OmiGlassPanelView.h"

#import <React/RCTViewManager.h>
#import <QuartzCore/QuartzCore.h>

static const CGFloat defaultCornerRadius = 22.0;
// The HUD material is a dark, behind-window vibrancy: whatever the window
// floats over shows through, darkened. A constant light scrim would flatten
// that; a modest black scrim keeps the dark base consistent even over bright
// content so the light React ink stays readable no matter what is behind.
static const CGFloat OmiGlassScrimAlpha = 0.25;
static const CGFloat OmiGlassEdgeAlpha = 0.10;
static const CGFloat OmiGlassSheenAlpha = 0.4;
static const CGFloat OmiGlassSheenHeight = 1.0;

static NSAppearance *OmiInkGlassAppearance(void)
{
  // Dark chrome: the HUD material must be evaluated in a dark appearance or
  // Aqua renders it light, which starves the light React ink of contrast.
  return [NSAppearance appearanceNamed:NSAppearanceNameDarkAqua];
}

@interface OmiGlassPanelView ()

{
  CGFloat _glassCornerRadius;
}

@property (nonatomic, strong) NSVisualEffectView *material;
@property (nonatomic, strong) NSView *fallback;
@property (nonatomic, strong) CALayer *scrim;
@property (nonatomic, strong) CALayer *sheen;
@property (nonatomic, strong, nullable) id accessibilityObserver;

@end

// Fade content itself so the existing window material remains uninterrupted.
@interface OmiScrollFadeView : RCTView
@property (nonatomic) BOOL fadeVisible;
@property (nonatomic, strong) CAGradientLayer *contentMask;
@end

@implementation OmiScrollFadeView

- (void)setFadeVisible:(BOOL)fadeVisible
{
  _fadeVisible = fadeVisible;
  self.needsLayout = YES;
}

- (void)layout
{
  [super layout];
  self.wantsLayer = YES;
  CGFloat height = NSHeight(self.bounds);
  if (!self.fadeVisible || height <= 0) {
    self.layer.mask = nil;
    return;
  }
  if (self.contentMask == nil) {
    self.contentMask = [CAGradientLayer layer];
    self.contentMask.colors = @[
      (id)NSColor.clearColor.CGColor, (id)NSColor.blackColor.CGColor,
      (id)NSColor.blackColor.CGColor, (id)NSColor.clearColor.CGColor
    ];
  }
  CGFloat fade = MIN(48.0, height / 4.0);
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  self.contentMask.frame = self.bounds;
  self.contentMask.startPoint = CGPointMake(0.5, self.isFlipped ? 0 : 1);
  self.contentMask.endPoint = CGPointMake(0.5, self.isFlipped ? 1 : 0);
  self.contentMask.locations = @[
    @0, @(fade / height), @(MAX(fade / height, 1 - fade / height)), @1
  ];
  self.layer.mask = self.contentMask;
  [CATransaction commit];
}

@end

@interface OmiScrollFadeManager : RCTViewManager
@end

@implementation OmiScrollFadeManager
RCT_EXPORT_MODULE(OmiScrollFade)
RCT_EXPORT_VIEW_PROPERTY(fadeVisible, BOOL)
- (NSView *)view { return [[OmiScrollFadeView alloc] initWithFrame:NSZeroRect]; }
+ (BOOL)requiresMainQueueSetup { return YES; }
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

  // This is a window backdrop, not a floating control. NSGlassEffectView
  // requires a contentView; Apple explicitly advises against placing it
  // behind content as a sibling (WWDC25, Build an AppKit app, 18:26).
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
  // Window/onboarding geometry changes must not animate a stale scrim through
  // the content. React owns content motion; the backdrop tracks bounds exactly.
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  self.material.frame = self.bounds;
  self.fallback.frame = self.bounds;
  self.scrim.frame = self.bounds;
  self.sheen.frame = NSMakeRect(0, NSMaxY(self.bounds) - OmiGlassSheenHeight, NSWidth(self.bounds),
      OmiGlassSheenHeight);
  [CATransaction commit];
}

- (void)applyAccessibilityAppearance
{
  BOOL reduceTransparency = NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceTransparency;
  self.material.hidden = reduceTransparency;
  self.fallback.hidden = !reduceTransparency;
  self.appearance = OmiInkGlassAppearance();
  [self.appearance performAsCurrentDrawingAppearance:^{
    self.fallback.layer.backgroundColor =
        [NSColor colorWithCalibratedWhite:0.11 alpha:1.0].CGColor;
    CGFloat alpha = reduceTransparency ? 1.0 : OmiGlassScrimAlpha;
    self.scrim.backgroundColor = [NSColor.blackColor colorWithAlphaComponent:alpha].CGColor;
    self.sheen.hidden = reduceTransparency;
    self.sheen.backgroundColor = [NSColor.whiteColor colorWithAlphaComponent:OmiGlassSheenAlpha].CGColor;
    self.layer.borderColor = [NSColor.whiteColor colorWithAlphaComponent:OmiGlassEdgeAlpha].CGColor;
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
