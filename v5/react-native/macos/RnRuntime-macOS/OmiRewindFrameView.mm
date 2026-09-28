#import "OmiRewindFrameView.h"

#import <React/RCTViewManager.h>

@interface OmiRewindFrameView ()
{
  NSImageView *_imageView;
  uint64_t _generation;
}
@end

@implementation OmiRewindFrameView

- (instancetype)initWithFrame:(NSRect)frameRect
{
  if ((self = [super initWithFrame:frameRect]) == nil) {
    return nil;
  }
  _generation = 0;
  _imageView = [[NSImageView alloc] initWithFrame:self.bounds];
  _imageView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
  _imageView.imageScaling = NSImageScaleProportionallyUpOrDown;
  _imageView.wantsLayer = YES;
  [self addSubview:_imageView];
  return self;
}

// The preview is presentation only; clicks pass through to the page below.
- (NSView *)hitTest:(NSPoint)point
{
  return nil;
}

- (void)setImageBase64:(NSString *)imageBase64
{
  _generation += 1;
  uint64_t generation = _generation;
  if (imageBase64.length == 0) {
    _imageView.image = nil;
    return;
  }
  NSData *payload = [[NSData alloc] initWithBase64EncodedString:imageBase64 options:0];
  if (payload == nil) {
    _imageView.image = nil;
    return;
  }
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSImage *decoded = [[NSImage alloc] initWithData:payload];
    dispatch_async(dispatch_get_main_queue(), ^{
      if (generation != self->_generation || self->_imageView == nil) {
        return;
      }
      self->_imageView.image = decoded;
    });
  });
}

@end

@interface OmiRewindFrameManager : RCTViewManager

@end

@implementation OmiRewindFrameManager

RCT_EXPORT_MODULE(OmiRewindFrame)

RCT_EXPORT_VIEW_PROPERTY(imageBase64, NSString)

- (NSView *)view
{
  return [[OmiRewindFrameView alloc] initWithFrame:NSZeroRect];
}

+ (BOOL)requiresMainQueueSetup
{
  return YES;
}

@end
