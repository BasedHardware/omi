#import <Foundation/Foundation.h>

static inline BOOL OmiAuthMobileCallbackIsValid(NSURL *url, NSString *state) {
  if (url == nil) return NO;
  NSURLComponents *callback = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO];
  if (callback == nil || state.length == 0 ||
      ![callback.scheme.lowercaseString isEqualToString:@"omi-rnruntime"] ||
      ![callback.host.lowercaseString isEqualToString:@"auth"] ||
      ![callback.percentEncodedPath isEqualToString:@"/callback"] ||
      callback.user != nil || callback.password != nil || callback.port != nil || callback.fragment != nil) return NO;
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  for (NSURLQueryItem *item in callback.queryItems) {
    if (values[item.name] != nil || item.value == nil) return NO;
    values[item.name] = item.value;
  }
  return [values[@"state"] isEqualToString:state] && values[@"code"].length > 0 && values[@"error"] == nil;
}
