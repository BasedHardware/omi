#import "OmiGlassPanelView.h"

#import <React/RCTViewManager.h>

static const CGFloat OmiGlassCornerRadius = 22.0;
static const CGFloat OmiGlassScrimAlpha = 0.14;

@interface OmiGlassPanelView ()

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
  self.appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];
  self.layer.cornerRadius = OmiGlassCornerRadius;
  self.layer.cornerCurve = kCACornerCurveContinuous;
  self.layer.borderWidth = 1.0;
  self.layer.borderColor = [NSColor.labelColor colorWithAlphaComponent:0.06].CGColor;
  self.layer.shadowColor = NSColor.blackColor.CGColor;
  self.layer.shadowRadius = 34.0;
  self.layer.shadowOpacity = 0.24;
  self.layer.shadowOffset = CGSizeMake(0.0, -10.0);

  self.material = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
  self.material.material = NSVisualEffectMaterialHUDWindow;
  self.material.blendingMode = NSVisualEffectBlendingModeBehindWindow;
  self.material.state = NSVisualEffectStateActive;
  self.material.wantsLayer = YES;
  self.material.layer.cornerRadius = OmiGlassCornerRadius;
  self.material.layer.cornerCurve = kCACornerCurveContinuous;
  self.material.layer.masksToBounds = YES;
  [self addSubview:self.material];

  self.fallback = [[NSView alloc] initWithFrame:self.bounds];
  self.fallback.wantsLayer = YES;
  self.fallback.layer.cornerRadius = OmiGlassCornerRadius;
  self.fallback.layer.cornerCurve = kCACornerCurveContinuous;
  self.fallback.layer.masksToBounds = YES;
  [self addSubview:self.fallback];

  self.scrim = [CALayer layer];
  self.scrim.cornerRadius = OmiGlassCornerRadius;
  self.scrim.cornerCurve = kCACornerCurveContinuous;
  [self.material.layer addSublayer:self.scrim];

  self.sheen = [CALayer layer];
  self.sheen.backgroundColor = [NSColor.whiteColor colorWithAlphaComponent:0.5].CGColor;
  [self.material.layer addSublayer:self.sheen];

  __weak OmiGlassPanelView *weakSelf = self;
  self.accessibilityObserver =
      [NSWorkspace.sharedWorkspace.notificationCenter
          addObserverForName:NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification
                      object:nil
                       queue:NSOperationQueue.mainQueue
                  usingBlock:^(__unused NSNotification *note) {
    [weakSelf applyAccessibilityAppearance];
  }];
  [self applyAccessibilityAppearance];
  return self;
}

- (void)dealloc
{
  if (self.accessibilityObserver != nil) {
    [NSWorkspace.sharedWorkspace.notificationCenter removeObserver:self.accessibilityObserver];
  }
}

- (BOOL)acceptsFirstMouse:(NSEvent *)event
{
  return YES;
}

- (void)layout
{
  [super layout];
  self.material.frame = self.bounds;
  self.fallback.frame = self.bounds;
  self.scrim.frame = self.bounds;
  self.sheen.frame = NSMakeRect(0.0, NSMaxY(self.bounds) - 1.0, NSWidth(self.bounds), 1.0);
  self.layer.shadowPath = [NSBezierPath bezierPathWithRoundedRect:self.bounds
                                                          xRadius:OmiGlassCornerRadius
                                                          yRadius:OmiGlassCornerRadius]
                              .CGPath;
}

- (void)applyAccessibilityAppearance
{
  BOOL reduceTransparency = NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceTransparency;
  self.material.hidden = reduceTransparency;
  self.fallback.hidden = !reduceTransparency;
  self.fallback.layer.backgroundColor = NSColor.controlBackgroundColor.CGColor;
  CGFloat alpha = reduceTransparency ? 1.0 : OmiGlassScrimAlpha;
  self.scrim.backgroundColor = [NSColor.controlBackgroundColor colorWithAlphaComponent:alpha].CGColor;
}

@end

@interface OmiGlassPanelManager : RCTViewManager

@end

@implementation OmiGlassPanelManager

RCT_EXPORT_MODULE(OmiGlassPanel)

- (NSView *)view
{
  return [[OmiGlassPanelView alloc] initWithFrame:NSZeroRect];
}

+ (BOOL)requiresMainQueueSetup
{
  return YES;
}

@end
