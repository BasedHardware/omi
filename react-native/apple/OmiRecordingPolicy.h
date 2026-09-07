#import <Foundation/Foundation.h>
#import <math.h>

static BOOL OmiRecordingCapturedAtValid(id value) {
  if (value == nil) return YES;
  if (![value isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID()) return NO;
  double number = [value doubleValue];
  return isfinite(number) && number >= 0 && number <= 8640000000000000.0 && number == floor(number);
}
static BOOL OmiRecordingCapturedAtMatches(id expected, id actual) {
  return OmiRecordingCapturedAtValid(expected) && OmiRecordingCapturedAtValid(actual)
    && (expected == nil ? actual == nil : [expected isEqual:actual]);
}

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

static BOOL OmiRememberedIdentity(id identifier, id name) {
  return [identifier isKindOfClass:NSString.class] && [identifier length] > 0 && [identifier length] <= 128 && [name isKindOfClass:NSString.class] && [name length] > 0 && [name length] <= 256;
}
static BOOL OmiRememberedCurrent(NSUInteger ticket, NSUInteger generation, NSString *expectedLogin, NSString *currentLogin, BOOL ready) {
  return ticket == generation && ready && expectedLogin.length > 0 && [expectedLogin isEqual:currentLogin];
}

static NSDictionary *OmiRememberedRefreshSession(NSDictionary *refreshed, NSDictionary *current) {
  NSMutableDictionary *merged = [refreshed mutableCopy];
  [merged removeObjectForKey:@"rememberedDevice"];
  if (current[@"rememberedDevice"] != nil) merged[@"rememberedDevice"] = current[@"rememberedDevice"];
  return merged;
}
