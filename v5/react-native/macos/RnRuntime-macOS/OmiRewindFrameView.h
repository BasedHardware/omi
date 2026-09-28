#import <React/RCTView.h>

// Renders a Rewind capture preview from the base64 JPEG payload the JS side
// already holds. This bypasses RN's URL image pipeline on purpose: on this
// react-native-macOS, both the data: and file: request handlers pass a nil
// request token to RCTNetworkTask (their weak operation reference is never
// assigned), which fatals dev builds with "Unrecognized request token: (null)"
// and fails the load in release builds.
@interface OmiRewindFrameView : RCTView

- (void)setImageBase64:(NSString *)imageBase64;

@end
