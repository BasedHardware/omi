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

static BOOL OmiRecordingRetryableOwnershipStatus(NSInteger status) {
  return status == 408 || status == 429 || (status >= 500 && status <= 599);
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

static NSDictionary *OmiRecordingInitializeLogin(NSDictionary *session) {
  if (session == nil) return nil;
  if ([session[@"journalLogin"] isKindOfClass:NSString.class] && [session[@"journalLogin"] length] > 0) return session;
  NSMutableDictionary *initialized = [session mutableCopy];
  initialized[@"journalLogin"] = NSUUID.UUID.UUIDString.lowercaseString;
  return initialized;
}

static NSDictionary *OmiRecordingLocalIdentity(NSDictionary *session, NSDictionary *claims) {
  NSString *uid = [session[@"tokenUserId"] isKindOfClass:NSString.class] ? session[@"tokenUserId"] : nil;
  NSString *login = [session[@"journalLogin"] isKindOfClass:NSString.class] ? session[@"journalLogin"] : nil;
  NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"];
  if (uid.length == 0 || uid.length > 128 || [uid rangeOfCharacterFromSet:allowed.invertedSet].location != NSNotFound || login.length == 0 || login.length > 128) return nil;
  if (![claims[@"aud"] isEqual:@"based-hardware"] || ![claims[@"iss"] isEqual:@"https://securetoken.google.com/based-hardware"] || ![claims[@"sub"] isEqual:uid] || (claims[@"user_id"] != nil && ![claims[@"user_id"] isEqual:uid])) return nil;
  return @{@"uid":uid,@"login":login};
}
