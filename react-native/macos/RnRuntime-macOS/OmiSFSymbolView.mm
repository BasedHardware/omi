#import "OmiSFSymbolView.h"

#import <React/RCTViewManager.h>

static NSColor *OmiSymbolColorFromHex(NSString *value)
{
  if (value.length < 7 || ![value hasPrefix:@"#"]) {
    return NSColor.labelColor;
  }
  unsigned int rgb = 0;
  NSScanner *scanner = [NSScanner scannerWithString:[value substringFromIndex:1]];
  if (![scanner scanHexInt:&rgb]) {
    return NSColor.labelColor;
  }
  return [NSColor colorWithSRGBRed:((rgb >> 16) & 0xff) / 255.0
                             green:((rgb >> 8) & 0xff) / 255.0
                              blue:(rgb & 0xff) / 255.0
                             alpha:1.0];
}

@interface OmiSFSymbolView ()

{
  CGFloat _symbolSize;
}

@property (nonatomic, copy) NSString *symbolName;
@property (nonatomic, copy) NSString *symbolColor;
@property (nonatomic, strong) NSImageView *imageView;

@end

@implementation OmiSFSymbolView

- (instancetype)initWithFrame:(NSRect)frameRect
{
  self = [super initWithFrame:frameRect];
  if (self == nil) {
    return nil;
  }
  _symbolSize = 16.0;
  self.imageView = [[NSImageView alloc] initWithFrame:self.bounds];
  self.imageView.imageScaling = NSImageScaleProportionallyUpOrDown;
  self.imageView.wantsLayer = YES;
  [self addSubview:self.imageView];
  return self;
}

- (NSView *)hitTest:(NSPoint)point
{
  return [super hitTest:point];
}

- (void)layout
{
  [super layout];
  self.imageView.frame = self.bounds;
}

- (void)setSymbolName:(NSString *)symbolName
{
  _symbolName = [symbolName copy];
  [self applySymbol];
}

- (void)setSymbolSize:(CGFloat)symbolSize
{
  _symbolSize = symbolSize > 0 ? symbolSize : 16.0;
  [self applySymbol];
}

- (void)setSymbolColor:(NSString *)symbolColor
{
  _symbolColor = [symbolColor copy];
  [self applySymbol];
}

- (void)applySymbol
{
  NSString *name = self.symbolName.length > 0 ? self.symbolName : @"questionmark";
  NSImage *image = [NSImage imageWithSystemSymbolName:name accessibilityDescription:name];
  NSImageSymbolConfiguration *configuration =
      [NSImageSymbolConfiguration configurationWithPointSize:_symbolSize weight:NSFontWeightMedium];
  self.imageView.image = [image imageWithSymbolConfiguration:configuration];
  self.imageView.contentTintColor = OmiSymbolColorFromHex(self.symbolColor);
}

@end

@interface OmiSFSymbolManager : RCTViewManager

@end

@implementation OmiSFSymbolManager

RCT_EXPORT_MODULE(OmiSFSymbol)

RCT_EXPORT_VIEW_PROPERTY(symbolName, NSString)
RCT_EXPORT_VIEW_PROPERTY(symbolSize, CGFloat)
RCT_EXPORT_VIEW_PROPERTY(symbolColor, NSString)

- (NSView *)view
{
  return [[OmiSFSymbolView alloc] initWithFrame:NSZeroRect];
}

+ (BOOL)requiresMainQueueSetup
{
  return YES;
}

@end
