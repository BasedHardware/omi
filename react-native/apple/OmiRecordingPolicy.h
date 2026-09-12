#import <Foundation/Foundation.h>
#import <math.h>

#include "omi_backend_recording.h"

static BOOL OmiRecordingCapturedAtValid(id value) {
  if (value == nil) return YES;
  if (![value isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID()) return NO;
  return omi_backend_recording_captured_at_valid([value doubleValue]) == 1;
}
static BOOL OmiRecordingCapturedAtMatches(id expected, id actual) {
  if (!OmiRecordingCapturedAtValid(expected) || !OmiRecordingCapturedAtValid(actual)) return NO;
  return omi_backend_recording_captured_at_equal(
    expected != nil ? 1 : 0, expected != nil ? [expected doubleValue] : 0.0,
    actual != nil ? 1 : 0, actual != nil ? [actual doubleValue] : 0.0) == 1;
}

static BOOL OmiRecordingRetryableOwnershipStatus(NSInteger status) {
  return omi_backend_recording_retryable_status((int32_t)status) == 1;
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
  return omi_backend_recording_same_context(
    [expectedLogin isKindOfClass:NSString.class] ? expectedLogin.UTF8String : nullptr,
    [currentLogin isKindOfClass:NSString.class] ? currentLogin.UTF8String : nullptr,
    [expectedOrigin isKindOfClass:NSString.class] ? expectedOrigin.UTF8String : nullptr,
    [currentOrigin isKindOfClass:NSString.class] ? currentOrigin.UTF8String : nullptr) == 1;
}

static BOOL OmiRememberedIdentity(id identifier, id name) {
  return omi_backend_recording_remembered_identity(
    [identifier isKindOfClass:NSString.class] ? (const char *)[identifier UTF8String] : nullptr,
    [name isKindOfClass:NSString.class] ? (const char *)[name UTF8String] : nullptr) == 1;
}
static BOOL OmiRememberedCurrent(NSUInteger ticket, NSUInteger generation, NSString *expectedLogin, NSString *currentLogin, BOOL ready) {
  return omi_backend_recording_remembered_current(
    (uint64_t)ticket, (uint64_t)generation,
    [expectedLogin isKindOfClass:NSString.class] ? expectedLogin.UTF8String : nullptr,
    [currentLogin isKindOfClass:NSString.class] ? currentLogin.UTF8String : nullptr,
    ready ? 1 : 0) == 1;
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
