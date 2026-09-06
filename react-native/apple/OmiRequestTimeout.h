#import <Foundation/Foundation.h>

static NSTimeInterval OmiRequestTimeout(NSString *method, NSURL *url) {
  NSArray<NSString *> *parts = [url.path componentsSeparatedByString:@"/"];
  return [method isEqualToString:@"POST"] && parts.count == 5 &&
    [parts[1] isEqualToString:@"v1"] && [parts[2] isEqualToString:@"device-sessions"] &&
    parts[3].length > 0 && [parts[4] isEqualToString:@"transcribe"] ? 150 : 60;
}
