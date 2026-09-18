#pragma once
#import <AppKit/AppKit.h>

// Host tests substitute only React's base view; AppKit and the production
// material/layout implementation remain real.
@interface RCTView : NSView
@end
