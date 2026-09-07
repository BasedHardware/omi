#import <Foundation/Foundation.h>

static BOOL OmiRecordingOffline(NSError *error) {
  if (![error.domain isEqual:NSURLErrorDomain]) return NO;
  switch (error.code) {
    case NSURLErrorTimedOut:
    case NSURLErrorCannotFindHost:
    case NSURLErrorCannotConnectToHost:
    case NSURLErrorNetworkConnectionLost:
    case NSURLErrorDNSLookupFailed:
    case NSURLErrorNotConnectedToInternet:
      return YES;
    default:
      return NO;
  }
}
static BOOL OmiRecordingSameContext(NSString *expectedLogin, NSString *currentLogin, NSString *expectedOrigin, NSString *currentOrigin) {
  return expectedLogin.length > 0 && [expectedLogin isEqual:currentLogin] && expectedOrigin.length > 0 && [expectedOrigin isEqual:currentOrigin];
}
