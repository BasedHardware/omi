#import <React/RCTView.h>

@interface OmiSFSymbolView : RCTView

- (void)setSymbolName:(NSString *)symbolName;
- (void)setSymbolSize:(CGFloat)symbolSize;
- (void)setSymbolColor:(NSString *)symbolColor;

@end
