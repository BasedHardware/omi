#import "OmiAuthModule.h"

#import <AppKit/AppKit.h>
#import <AuthenticationServices/AuthenticationServices.h>
#import <CommonCrypto/CommonDigest.h>
#import <LocalAuthentication/LocalAuthentication.h>
#import <Security/Security.h>
#import <arpa/inet.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <string.h>
#import <unistd.h>

static NSString *const OmiAuthKeychainService = @"com.omi.rnruntime.firebase-rest-session";
static NSString *const OmiAuthKeychainAccount = @"firebase-rest-tokens";
static NSString *const OmiOnboardingCompletedKey = @"omi.onboarding.completed";

static BOOL OmiAuthIgnoreEnvironmentCloudTokens = NO;

BOOL OmiAuthEnvironmentCloudTokensIgnored(void) {
  @synchronized (OmiAuthKeychainService) {
    return OmiAuthIgnoreEnvironmentCloudTokens;
  }
}

void OmiAuthSetEnvironmentCloudTokensIgnored(BOOL ignored) {
  @synchronized (OmiAuthKeychainService) {
    OmiAuthIgnoreEnvironmentCloudTokens = ignored;
  }
}


static NSString *OmiAuthBase64URL(NSData *data) {
  NSString *value = [data base64EncodedStringWithOptions:0];
  value = [value stringByReplacingOccurrencesOfString:@"+" withString:@"-"];
  value = [value stringByReplacingOccurrencesOfString:@"/" withString:@"_"];
  return [value stringByReplacingOccurrencesOfString:@"=" withString:@""];
}

static NSString *OmiAuthRandomValue(void) {
  uint8_t bytes[32];
  if (SecRandomCopyBytes(kSecRandomDefault, sizeof(bytes), bytes) != errSecSuccess) return nil;
  return OmiAuthBase64URL([NSData dataWithBytes:bytes length:sizeof(bytes)]);
}

static NSString *OmiAuthCodeChallenge(NSString *verifier) {
  NSData *data = [verifier dataUsingEncoding:NSUTF8StringEncoding];
  uint8_t digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  return OmiAuthBase64URL([NSData dataWithBytes:digest length:sizeof(digest)]);
}

static int OmiAuthListenLoopback(uint16_t *portOut) {
  int fileDescriptor = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (fileDescriptor < 0) return -1;
  int reuse = 1;
  setsockopt(fileDescriptor, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  struct sockaddr_in address = {};
  address.sin_len = sizeof(address);
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = 0;
  if (bind(fileDescriptor, (struct sockaddr *)&address, sizeof(address)) != 0 ||
      listen(fileDescriptor, 16) != 0) {
    close(fileDescriptor);
    return -1;
  }
  socklen_t length = sizeof(address);
  if (getsockname(fileDescriptor, (struct sockaddr *)&address, &length) != 0) {
    close(fileDescriptor);
    return -1;
  }
  if (portOut != NULL) *portOut = ntohs(address.sin_port);
  return fileDescriptor;
}

static BOOL OmiAuthPeerIsLoopback(int client) {
  struct sockaddr_storage peer = {};
  socklen_t length = sizeof(peer);
  if (getpeername(client, (struct sockaddr *)&peer, &length) != 0) return NO;
  if (peer.ss_family == AF_INET) {
    struct sockaddr_in *address = (struct sockaddr_in *)&peer;
    return address->sin_addr.s_addr == htonl(INADDR_LOOPBACK);
  }
  if (peer.ss_family == AF_INET6) {
    struct sockaddr_in6 *address = (struct sockaddr_in6 *)&peer;
    return IN6_IS_ADDR_LOOPBACK(&address->sin6_addr);
  }
  return NO;
}

// Aside cannot close a tab it did not open. After a valid code, replace
// the leftover product page with about:blank and try close; the app then
// cancels ASWebAuthenticationSession and comes forward.
static NSString *OmiAuthBlankCallbackHTML(void) {
  return @"<!doctype html><html><head><meta charset='utf-8'><script>location.replace('about:blank');try{window.close();}catch(e){}</script></head><body></body></html>";
}

static NSURL *OmiAuthValidatedCallbackURL(NSString *request, NSString *expectedState, uint16_t port) {
  NSString *requestLine = [[request componentsSeparatedByString:@"\r\n"] firstObject];
  NSArray<NSString *> *rawParts = [requestLine componentsSeparatedByCharactersInSet:
      NSCharacterSet.whitespaceCharacterSet];
  NSMutableArray<NSString *> *parts = [NSMutableArray array];
  for (NSString *part in rawParts) if (part.length > 0) [parts addObject:part];
  if (parts.count != 3 || ![parts[0] isEqualToString:@"GET"] ||
      (![parts[2] isEqualToString:@"HTTP/1.0"] && ![parts[2] isEqualToString:@"HTTP/1.1"])) {
    return nil;
  }
  NSString *target = parts[1];
  if (![target hasPrefix:@"/"] || [target hasPrefix:@"//"] || [target containsString:@"#"]) return nil;
  NSURLComponents *components = [NSURLComponents componentsWithString:
      [NSString stringWithFormat:@"http://127.0.0.1:%u%@", port, target]];
  if (components == nil || ![components.path isEqualToString:@"/callback"] ||
      ![components.percentEncodedPath isEqualToString:@"/callback"] ||
      components.fragment.length > 0) {
    return nil;
  }
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  for (NSURLQueryItem *item in components.queryItems) if (item.value != nil) values[item.name] = item.value;
  if (![values[@"state"] isEqualToString:expectedState] || values[@"code"].length == 0) return nil;
  return components.URL;
}

static NSURL *OmiAuthAcceptCallback(int listener, uint16_t port, NSTimeInterval timeout, NSString *expectedState) {
  if (listener < 0) return nil;
  NSTimeInterval deadline = NSDate.date.timeIntervalSince1970 + timeout;
  while (NSDate.date.timeIntervalSince1970 < deadline) {
    NSTimeInterval remaining = deadline - NSDate.date.timeIntervalSince1970;
    fd_set readSet;
    FD_ZERO(&readSet);
    FD_SET(listener, &readSet);
    struct timeval wait = {
      .tv_sec = (int)remaining,
      .tv_usec = (int)((remaining - (int)remaining) * 1000000),
    };
    if (select(listener + 1, &readSet, NULL, NULL, &wait) <= 0) return nil;
    struct sockaddr_storage acceptedPeer = {};
    socklen_t acceptedLength = sizeof(acceptedPeer);
    int client = accept(listener, (struct sockaddr *)&acceptedPeer, &acceptedLength);
    if (client < 0) continue;
    if (!OmiAuthPeerIsLoopback(client)) {
      close(client);
      continue;
    }
    struct timeval receiveTimeout = {.tv_sec = 5, .tv_usec = 0};
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &receiveTimeout, sizeof(receiveTimeout));
    char buffer[4096];
    ssize_t count = recv(client, buffer, sizeof(buffer) - 1, 0);
    NSString *request = nil;
    if (count > 0) {
      buffer[count] = 0;
      request = [[NSString alloc] initWithBytes:buffer
                                         length:(NSUInteger)count
                                       encoding:NSUTF8StringEncoding];
    }
    NSURL *callbackURL = OmiAuthValidatedCallbackURL(request ?: @"", expectedState, port);
    if (callbackURL == nil) {
      const char *invalid =
          "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain; charset=utf-8\r\n"
          "Connection: close\r\nContent-Length: 16\r\n\r\nInvalid callback";
      send(client, invalid, strlen(invalid), 0);
      close(client);
      continue;
    }
    NSData *page = [OmiAuthBlankCallbackHTML() dataUsingEncoding:NSUTF8StringEncoding];
    NSString *head = [NSString stringWithFormat:
        @"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
         "Connection: close\r\nContent-Length: %lu\r\n\r\n",
        (unsigned long)page.length];
    NSMutableData *payload = [[head dataUsingEncoding:NSUTF8StringEncoding] mutableCopy];
    [payload appendData:page];
    send(client, payload.bytes, (size_t)payload.length, 0);
    close(client);
    return callbackURL;
  }
  return nil;
}

static NSDictionary *OmiAuthKeychainQuery(void) {
  return @{
    (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService : OmiAuthKeychainService,
    (__bridge id)kSecAttrAccount : OmiAuthKeychainAccount,
  };
}

static NSDictionary *OmiAuthStoredSession(void) {
  NSMutableDictionary *query = [OmiAuthKeychainQuery() mutableCopy];
  query[(__bridge id)kSecReturnData] = @YES;
  query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
  query[(__bridge id)kSecUseAuthenticationUI] = (__bridge id)kSecUseAuthenticationUIFail;
  LAContext *context = [[LAContext alloc] init];
  context.interactionNotAllowed = YES;
  query[(__bridge id)kSecUseAuthenticationContext] = context;
  CFTypeRef result = NULL;
  OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
  if (status != errSecSuccess || result == NULL) return nil;
  NSData *data = CFBridgingRelease(result);
  NSDictionary *session = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [session isKindOfClass:NSDictionary.class] ? session : nil;
}

static OSStatus OmiAuthClearSession(void) {
  return SecItemDelete((__bridge CFDictionaryRef)OmiAuthKeychainQuery());
}

static BOOL OmiAuthSessionTokenIsFresh(NSDictionary *session) {
  NSString *token = [session[@"idToken"] isKindOfClass:NSString.class] ? session[@"idToken"] : nil;
  NSNumber *expiryTime = [session[@"expiryTime"] isKindOfClass:NSNumber.class] ? session[@"expiryTime"] : nil;
  return token.length > 0 &&
      (expiryTime == nil || expiryTime.doubleValue > NSDate.date.timeIntervalSince1970 + 60);
}

static BOOL OmiAuthRefreshFailureIsDefinitive(NSInteger status, NSDictionary *json) {
  if (status == 401 || status == 403) return YES;
  NSDictionary *error = [json[@"error"] isKindOfClass:NSDictionary.class] ? json[@"error"] : nil;
  NSString *message = [error[@"message"] isKindOfClass:NSString.class] ? error[@"message"] : nil;
  if (status != 400 || message.length == 0) return NO;
  NSSet<NSString *> *definitive = [NSSet setWithArray:@[
    @"INVALID_REFRESH_TOKEN",
    @"TOKEN_EXPIRED",
    @"USER_DISABLED",
    @"USER_NOT_FOUND",
  ]];
  return [definitive containsObject:message.uppercaseString];
}

static NSString *OmiAuthFormEncode(NSString *value) {
  NSMutableCharacterSet *allowed = [NSCharacterSet.alphanumericCharacterSet mutableCopy];
  [allowed addCharactersInString:@"-._~"];
  return [value stringByAddingPercentEncodingWithAllowedCharacters:allowed] ?: @"";
}

static NSDictionary *OmiAuthJWTPayload(NSString *token) {
  NSArray<NSString *> *parts = [token componentsSeparatedByString:@"."];
  if (parts.count < 2) return @{};
  NSString *value = [parts[1] stringByReplacingOccurrencesOfString:@"-" withString:@"+"];
  value = [value stringByReplacingOccurrencesOfString:@"_" withString:@"/"];
  while (value.length % 4 != 0) value = [value stringByAppendingString:@"="];
  NSData *data = [[NSData alloc] initWithBase64EncodedString:value options:0];
  NSDictionary *payload = data == nil ? nil : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [payload isKindOfClass:NSDictionary.class] ? payload : @{};
}

static BOOL OmiAuthStoreSession(NSString *idToken, NSString *refreshToken, NSNumber *expiresIn,
                                NSString *localId, NSString *firebaseApiKey) {
  NSDictionary *payload = OmiAuthJWTPayload(idToken);
  NSNumber *expiry = [payload[@"exp"] isKindOfClass:NSNumber.class]
      ? payload[@"exp"]
      : @(NSDate.date.timeIntervalSince1970 +
          (expiresIn.doubleValue > 0 ? expiresIn.doubleValue : 3600));
  NSString *userId = localId.length > 0 ? localId
      : ([payload[@"user_id"] isKindOfClass:NSString.class] ? payload[@"user_id"] : payload[@"sub"]);
  NSDictionary *session = @{
    @"idToken" : idToken,
    @"refreshToken" : refreshToken ?: @"",
    @"expiryTime" : expiry,
    @"tokenUserId" : userId ?: @"",
    @"firebaseApiKey" : firebaseApiKey ?: @"",
  };
  NSData *data = [NSJSONSerialization dataWithJSONObject:session options:0 error:nil];
  if (data == nil) return NO;
  NSDictionary *attributes = @{
    (__bridge id)kSecValueData : data,
    (__bridge id)kSecAttrAccessible : (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
  };
  NSDictionary *query = OmiAuthKeychainQuery();
  OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)attributes);
  if (status == errSecItemNotFound) {
    NSMutableDictionary *add = [query mutableCopy];
    [add addEntriesFromDictionary:attributes];
    status = SecItemAdd((__bridge CFDictionaryRef)add, NULL);
  }
  return status == errSecSuccess;
}

@interface OmiAuthModule () <ASWebAuthenticationPresentationContextProviding>
@property(nonatomic, strong) ASWebAuthenticationSession *authenticationSession;
@property(nonatomic) int loopbackListener;
@property(nonatomic) BOOL settled;
@property(nonatomic) BOOL signInCompleting;
@property(nonatomic) NSUInteger signInAttempt;
@property(nonatomic, copy) RCTPromiseRejectBlock pendingSignInReject;
@end

@implementation OmiAuthModule

RCT_EXPORT_MODULE(OmiAuth)

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (instancetype)init {
  self = [super init];
  if (self) _loopbackListener = -1;
  return self;
}

- (ASPresentationAnchor)presentationAnchorForWebAuthenticationSession:(ASWebAuthenticationSession *)session {
  return NSApp.keyWindow ?: NSApp.windows.firstObject;
}

- (void)closeLoopback {
  if (self.loopbackListener >= 0) {
    shutdown(self.loopbackListener, SHUT_RDWR);
    close(self.loopbackListener);
    self.loopbackListener = -1;
  }
}

- (void)performRequest:(NSURLRequest *)request completion:(void (^)(NSDictionary *, NSError *))completion {
  NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  configuration.HTTPCookieStorage = nil;
  NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration];
  [[session dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
        ? ((NSHTTPURLResponse *)response).statusCode : 0;
    NSDictionary *json = data == nil ? nil : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (error != nil || status < 200 || status >= 300 || ![json isKindOfClass:NSDictionary.class]) {
      NSError *failure = error ?: [NSError errorWithDomain:@"OmiAuth" code:status userInfo:nil];
      completion(nil, failure);
      return;
    }
    completion(json, nil);
  }] resume];
}

- (void)refreshStoredSession:(NSDictionary *)session
              firebaseApiKey:(NSString *)firebaseApiKey
                  completion:(void (^)(NSString *, NSError *))completion {
  NSString *refreshToken = session[@"refreshToken"];
  NSURLComponents *components = [NSURLComponents componentsWithString:
      @"https://securetoken.googleapis.com/v1/token"];
  components.queryItems = @[[NSURLQueryItem queryItemWithName:@"key" value:firebaseApiKey]];
  NSMutableURLRequest *refresh = [NSMutableURLRequest requestWithURL:components.URL];
  refresh.HTTPMethod = @"POST";
  [refresh setValue:@"application/x-www-form-urlencoded" forHTTPHeaderField:@"content-type"];
  NSString *body = [NSString stringWithFormat:@"grant_type=refresh_token&refresh_token=%@",
      OmiAuthFormEncode(refreshToken)];
  refresh.HTTPBody = [body dataUsingEncoding:NSUTF8StringEncoding];
  NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  configuration.HTTPCookieStorage = nil;
  NSURLSession *networkSession = [NSURLSession sessionWithConfiguration:configuration];
  [[networkSession dataTaskWithRequest:refresh completionHandler:
      ^(NSData *data, NSURLResponse *response, NSError *error) {
    NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
        ? ((NSHTTPURLResponse *)response).statusCode : 0;
    NSDictionary *json = data == nil ? nil : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (error != nil || status < 200 || status >= 300 || ![json isKindOfClass:NSDictionary.class]) {
      if (OmiAuthRefreshFailureIsDefinitive(status, json)) {
        OmiAuthClearSession();
        completion(nil, nil);
        return;
      }
      completion(nil, error ?: [NSError errorWithDomain:@"OmiAuth" code:status userInfo:nil]);
      return;
    }
    NSString *newIdToken = [json[@"id_token"] isKindOfClass:NSString.class] ? json[@"id_token"] : nil;
    NSString *newRefreshToken = [json[@"refresh_token"] isKindOfClass:NSString.class]
        ? json[@"refresh_token"] : nil;
    NSString *userId = [json[@"user_id"] isKindOfClass:NSString.class] ? json[@"user_id"] : session[@"tokenUserId"];
    NSNumber *expiresIn = [json[@"expires_in"] respondsToSelector:@selector(doubleValue)]
        ? @([json[@"expires_in"] doubleValue]) : @3600;
    if (newIdToken.length == 0 || newRefreshToken.length == 0 ||
        !OmiAuthStoreSession(newIdToken, newRefreshToken, expiresIn, userId, firebaseApiKey)) {
      completion(nil, [NSError errorWithDomain:@"OmiAuth" code:status userInfo:nil]);
      return;
    }
    completion(newIdToken, nil);
  }] resume];
}

- (void)resolveStoredToken:(void (^)(NSString *, NSError *))completion {
  NSDictionary *session = OmiAuthStoredSession();
  if (session == nil) {
    completion(nil, nil);
    return;
  }
  NSString *idToken = [session[@"idToken"] isKindOfClass:NSString.class] ? session[@"idToken"] : nil;
  if (OmiAuthSessionTokenIsFresh(session)) {
    completion(idToken, nil);
    return;
  }
  NSString *refreshToken = [session[@"refreshToken"] isKindOfClass:NSString.class]
      ? session[@"refreshToken"] : nil;
  if (refreshToken.length == 0) {
    OmiAuthClearSession();
    completion(nil, nil);
    return;
  }
  NSString *firebaseApiKey = [session[@"firebaseApiKey"] isKindOfClass:NSString.class]
      ? session[@"firebaseApiKey"] : nil;
  if (firebaseApiKey.length > 0) {
    [self refreshStoredSession:session firebaseApiKey:firebaseApiKey completion:completion];
    return;
  }
  NSMutableURLRequest *configuration = [NSMutableURLRequest requestWithURL:
      [NSURL URLWithString:@"https://api.omi.me/v1/config/api-keys"]];
  [self performRequest:configuration completion:^(NSDictionary *keys, NSError *keysError) {
    NSString *key = [keys[@"firebase_api_key"] isKindOfClass:NSString.class]
        ? keys[@"firebase_api_key"] : keys[@"firebaseApiKey"];
    if (keysError != nil || key.length == 0) {
      completion(nil, keysError ?: [NSError errorWithDomain:@"OmiAuth" code:0 userInfo:nil]);
      return;
    }
    [self refreshStoredSession:session firebaseApiKey:key completion:completion];
  }];
}

- (BOOL)isSignInAttemptCurrent:(NSUInteger)attempt {
  @synchronized (self) {
    return attempt == self.signInAttempt && !self.settled;
  }
}

- (void)bringOmiToFront {
  // The browser owned the foreground while the user signed in; hand it back.
  [NSApp activate];
  NSWindow *window = NSApp.keyWindow ?: NSApp.windows.firstObject;
  [window makeKeyAndOrderFront:nil];
}

- (void)finishSignInAttempt:(NSUInteger)attempt
                      value:(id)value
                       code:(NSString *)code
                    message:(NSString *)message
                      error:(NSError *)error
                    resolve:(RCTPromiseResolveBlock)resolve
                     reject:(RCTPromiseRejectBlock)reject {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{
      [self finishSignInAttempt:attempt value:value code:code message:message error:error
                        resolve:resolve reject:reject];
    });
    return;
  }
  @synchronized (self) {
    if (attempt != self.signInAttempt || self.settled) return;
    self.settled = YES;
    self.signInCompleting = NO;
    self.pendingSignInReject = nil;
  }
  [self.authenticationSession cancel];
  self.authenticationSession = nil;
  [self closeLoopback];
  if (code != nil) {
    reject(code, message, error);
    return;
  }
  OmiAuthSetEnvironmentCloudTokensIgnored(NO);
  resolve(value);
  [self bringOmiToFront];
}

- (void)finishWithTokenResponse:(NSDictionary *)tokenResponse
                         attempt:(NSUInteger)attempt
                         resolve:(RCTPromiseResolveBlock)resolve
                          reject:(RCTPromiseRejectBlock)reject {
  if (![self isSignInAttemptCurrent:attempt]) return;
  NSString *idToken = [tokenResponse[@"id_token"] isKindOfClass:NSString.class] ? tokenResponse[@"id_token"] : nil;
  if (idToken.length > 0) {
    NSString *refreshToken = [tokenResponse[@"refresh_token"] isKindOfClass:NSString.class]
        ? tokenResponse[@"refresh_token"] : tokenResponse[@"refreshToken"];
    NSNumber *expiresIn = [tokenResponse[@"expires_in"] respondsToSelector:@selector(doubleValue)]
        ? @([tokenResponse[@"expires_in"] doubleValue]) : @3600;
    NSString *localId = [tokenResponse[@"local_id"] isKindOfClass:NSString.class]
        ? tokenResponse[@"local_id"] : tokenResponse[@"localId"];
    NSString *firebaseApiKey = [tokenResponse[@"firebase_api_key"] isKindOfClass:NSString.class]
        ? tokenResponse[@"firebase_api_key"] : tokenResponse[@"firebaseApiKey"];
    if (refreshToken.length == 0 || firebaseApiKey.length > 0) {
      if (![self isSignInAttemptCurrent:attempt] ||
          !OmiAuthStoreSession(idToken, refreshToken, expiresIn, localId, firebaseApiKey)) {
        [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNCONFIGURED"
                          message:@"Could not store the Omi cloud session" error:nil
                          resolve:resolve reject:reject];
        return;
      }
      [self finishSignInAttempt:attempt value:@{@"signedIn" : @YES} code:nil message:nil error:nil
                        resolve:resolve reject:reject];
      return;
    }
    NSMutableURLRequest *configuration = [NSMutableURLRequest requestWithURL:
        [NSURL URLWithString:@"https://api.omi.me/v1/config/api-keys"]];
    [configuration setValue:[NSString stringWithFormat:@"Bearer %@", idToken]
         forHTTPHeaderField:@"authorization"];
    [self performRequest:configuration completion:^(NSDictionary *keys, NSError *keysError) {
      NSString *key = [keys[@"firebase_api_key"] isKindOfClass:NSString.class]
          ? keys[@"firebase_api_key"] : keys[@"firebaseApiKey"];
      if (![self isSignInAttemptCurrent:attempt]) return;
      if (keysError != nil || key.length == 0 ||
          !OmiAuthStoreSession(idToken, refreshToken, expiresIn, localId, key)) {
        [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                          message:@"Omi cloud could not preserve a refreshable session" error:keysError
                          resolve:resolve reject:reject];
        return;
      }
      [self finishSignInAttempt:attempt value:@{@"signedIn" : @YES} code:nil message:nil error:nil
                        resolve:resolve reject:reject];
    }];
    return;
  }
  NSString *customToken = [tokenResponse[@"custom_token"] isKindOfClass:NSString.class]
      ? tokenResponse[@"custom_token"] : nil;
  if (customToken.length == 0) {
    [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                      message:@"Omi cloud did not return a usable session" error:nil
                      resolve:resolve reject:reject];
    return;
  }
  NSMutableURLRequest *configuration = [NSMutableURLRequest requestWithURL:
      [NSURL URLWithString:@"https://api.omi.me/v1/config/api-keys"]];
  [configuration setValue:[NSString stringWithFormat:@"Bearer %@", customToken]
       forHTTPHeaderField:@"authorization"];
  [self performRequest:configuration completion:^(NSDictionary *keys, NSError *keysError) {
    if (![self isSignInAttemptCurrent:attempt]) return;
    NSString *firebaseKey = [keys[@"firebase_api_key"] isKindOfClass:NSString.class]
        ? keys[@"firebase_api_key"] : keys[@"firebaseApiKey"];
    if (keysError != nil || firebaseKey.length == 0) {
      [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                        message:@"Omi cloud could not establish a Firebase session" error:keysError
                        resolve:resolve reject:reject];
      return;
    }
    NSURLComponents *components = [NSURLComponents componentsWithString:
        @"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"];
    components.queryItems = @[[NSURLQueryItem queryItemWithName:@"key" value:firebaseKey]];
    NSMutableURLRequest *firebase = [NSMutableURLRequest requestWithURL:components.URL];
    firebase.HTTPMethod = @"POST";
    [firebase setValue:@"application/json" forHTTPHeaderField:@"content-type"];
    firebase.HTTPBody = [NSJSONSerialization dataWithJSONObject:@{
      @"token" : customToken,
      @"returnSecureToken" : @YES,
    } options:0 error:nil];
    [self performRequest:firebase completion:^(NSDictionary *tokens, NSError *firebaseError) {
      if (![self isSignInAttemptCurrent:attempt]) return;
      NSString *firebaseIdToken = [tokens[@"idToken"] isKindOfClass:NSString.class] ? tokens[@"idToken"] : nil;
      if (firebaseError != nil || firebaseIdToken.length == 0 ||
          !OmiAuthStoreSession(firebaseIdToken, tokens[@"refreshToken"], tokens[@"expiresIn"],
                               tokens[@"localId"], firebaseKey)) {
        [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                          message:@"Omi cloud could not establish a Firebase session" error:firebaseError
                          resolve:resolve reject:reject];
        return;
      }
      [self finishSignInAttempt:attempt value:@{@"signedIn" : @YES} code:nil message:nil error:nil
                        resolve:resolve reject:reject];
    }];
  }];
}

- (void)completeSignInWithCallback:(NSURL *)callbackURL
                             state:(NSString *)state
                          verifier:(NSString *)verifier
                       redirectURI:(NSString *)redirectURI
                           attempt:(NSUInteger)attempt
                           resolve:(RCTPromiseResolveBlock)resolve
                            reject:(RCTPromiseRejectBlock)reject {
  if (callbackURL == nil) {
    @synchronized (self) {
      if (attempt != self.signInAttempt || self.settled || self.signInCompleting) return;
      self.signInCompleting = YES;
    }
    [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                      message:@"Omi cloud sign in was cancelled or failed" error:nil
                      resolve:resolve reject:reject];
    return;
  }
  NSURLComponents *callback = [NSURLComponents componentsWithURL:callbackURL resolvingAgainstBaseURL:NO];
  NSURLComponents *redirect = [NSURLComponents componentsWithString:redirectURI];
  if (![callback.scheme.lowercaseString isEqualToString:@"http"] ||
      ![callback.host.lowercaseString isEqualToString:@"127.0.0.1"] ||
      ![callback.port isEqualToNumber:redirect.port] ||
      ![callback.path isEqualToString:@"/callback"] ||
      ![callback.percentEncodedPath isEqualToString:@"/callback"] || callback.fragment.length > 0 ||
      ![redirect.scheme.lowercaseString isEqualToString:@"http"] ||
      ![redirect.host.lowercaseString isEqualToString:@"127.0.0.1"] ||
      ![redirect.path isEqualToString:@"/callback"]) {
    return;
  }
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  for (NSURLQueryItem *item in callback.queryItems) if (item.value != nil) values[item.name] = item.value;
  if (![values[@"state"] isEqualToString:state] || values[@"code"].length == 0) return;
  @synchronized (self) {
    if (attempt != self.signInAttempt || self.settled || self.signInCompleting) return;
    self.signInCompleting = YES;
  }
  [self.authenticationSession cancel];
  self.authenticationSession = nil;
  [self closeLoopback];
  [self bringOmiToFront];
  NSURLComponents *form = [[NSURLComponents alloc] init];
  form.queryItems = @[
    [NSURLQueryItem queryItemWithName:@"grant_type" value:@"authorization_code"],
    [NSURLQueryItem queryItemWithName:@"code" value:values[@"code"]],
    [NSURLQueryItem queryItemWithName:@"redirect_uri" value:redirectURI],
    [NSURLQueryItem queryItemWithName:@"use_custom_token" value:@"true"],
    [NSURLQueryItem queryItemWithName:@"code_verifier" value:verifier],
  ];
  NSMutableURLRequest *exchange = [NSMutableURLRequest requestWithURL:
      [NSURL URLWithString:@"https://api.omi.me/v1/auth/token"]];
  exchange.HTTPMethod = @"POST";
  [exchange setValue:@"application/x-www-form-urlencoded" forHTTPHeaderField:@"content-type"];
  exchange.HTTPBody = [form.percentEncodedQuery dataUsingEncoding:NSUTF8StringEncoding];
  [self performRequest:exchange completion:^(NSDictionary *tokens, NSError *exchangeError) {
    if (![self isSignInAttemptCurrent:attempt]) return;
    if (exchangeError != nil) {
      [self finishSignInAttempt:attempt value:nil code:@"OMI_AUTH_UNAUTHORIZED"
                        message:@"Omi cloud token exchange failed" error:exchangeError
                        resolve:resolve reject:reject];
      return;
    }
    [self finishWithTokenResponse:tokens attempt:attempt resolve:resolve reject:reject];
  }];
}

RCT_REMAP_METHOD(hasCloudSession,
                 hasCloudSessionWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if (!OmiAuthEnvironmentCloudTokensIgnored()) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    if ([environment[@"OMI_CLOUD_API_TOKEN"] length] > 0 ||
        [environment[@"OMI_API_TOKEN"] length] > 0) {
      resolve(@YES);
      return;
    }
  }
  [self resolveStoredToken:^(NSString *token, NSError *error) {
    if (error != nil) {
      reject(@"OMI_AUTH_TRANSPORT", @"Omi cloud session could not be refreshed", error);
      return;
    }
    resolve(@(token.length > 0));
  }];
}

RCT_REMAP_METHOD(hasCompletedOnboarding,
                 hasCompletedOnboardingWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  resolve(@([NSUserDefaults.standardUserDefaults boolForKey:OmiOnboardingCompletedKey]));
}

RCT_REMAP_METHOD(markOnboardingComplete,
                 markOnboardingCompleteWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [NSUserDefaults.standardUserDefaults setBool:YES forKey:OmiOnboardingCompletedKey];
  resolve(nil);
}

RCT_REMAP_METHOD(signIn,
                 signInWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  dispatch_async(dispatch_get_main_queue(), ^{
    RCTPromiseRejectBlock previousReject = self.pendingSignInReject;
    self.signInAttempt += 1;
    NSUInteger attempt = self.signInAttempt;
    self.pendingSignInReject = nil;
    self.settled = YES;
    self.signInCompleting = NO;
    [self.authenticationSession cancel];
    self.authenticationSession = nil;
    [self closeLoopback];
    if (previousReject != nil) {
      previousReject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud sign in was cancelled", nil);
    }
    NSString *state = OmiAuthRandomValue();
    NSString *verifier = OmiAuthRandomValue();
    uint16_t port = 0;
    int listener = OmiAuthListenLoopback(&port);
    if (state.length == 0 || verifier.length == 0 || listener < 0 || port == 0) {
      if (listener >= 0) close(listener);
      reject(@"OMI_AUTH_UNCONFIGURED", @"Could not prepare Omi cloud sign in", nil);
      return;
    }
    self.settled = NO;
    self.signInCompleting = NO;
    self.pendingSignInReject = [reject copy];
    self.loopbackListener = listener;
    // api.omi.me accepts this loopback redirect. No custom URL scheme is
    // registered for this bundle, so the loopback listener is the bounce-back
    // and the auth sheet is cancelled programmatically once the code lands.
    NSString *redirectURI = [NSString stringWithFormat:@"http://127.0.0.1:%u/callback", port];
    NSURLComponents *authorize = [NSURLComponents componentsWithString:@"https://api.omi.me/v1/auth/authorize"];
    authorize.queryItems = @[
      [NSURLQueryItem queryItemWithName:@"provider" value:@"google"],
      [NSURLQueryItem queryItemWithName:@"redirect_uri" value:redirectURI],
      [NSURLQueryItem queryItemWithName:@"state" value:state],
      [NSURLQueryItem queryItemWithName:@"code_challenge" value:OmiAuthCodeChallenge(verifier)],
      [NSURLQueryItem queryItemWithName:@"code_challenge_method" value:@"S256"],
    ];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
      NSURL *callbackURL = OmiAuthAcceptCallback(listener, port, 180, state);
      dispatch_async(dispatch_get_main_queue(), ^{
        if (attempt != self.signInAttempt) return;
        [self completeSignInWithCallback:callbackURL
                                   state:state
                                verifier:verifier
                             redirectURI:redirectURI
                                 attempt:attempt
                                 resolve:resolve
                                  reject:reject];
      });
    });
    self.authenticationSession = [[ASWebAuthenticationSession alloc]
        initWithURL:authorize.URL callbackURLScheme:@"http"
        completionHandler:^(NSURL *callbackURL, NSError *__unused error) {
      if (callbackURL == nil) {
        return;
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        if (attempt != self.signInAttempt) return;
        [self completeSignInWithCallback:callbackURL
                                   state:state
                                verifier:verifier
                             redirectURI:redirectURI
                                 attempt:attempt
                                 resolve:resolve
                                  reject:reject];
      });
    }];
    self.authenticationSession.presentationContextProvider = self;
    self.authenticationSession.prefersEphemeralWebBrowserSession = YES;
    if (![self.authenticationSession start]) {
      [self completeSignInWithCallback:nil
                                 state:state
                              verifier:verifier
                           redirectURI:redirectURI
                               attempt:attempt
                               resolve:resolve
                                reject:reject];
    }
  });
}

RCT_REMAP_METHOD(signOut,
                 signOutWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  OSStatus status = OmiAuthClearSession();
  if (status == errSecSuccess || status == errSecItemNotFound) {
    OmiAuthSetEnvironmentCloudTokensIgnored(YES);
    resolve(@{@"signedOut" : @YES});
    return;
  }
  reject(@"OMI_AUTH_KEYCHAIN",
         @"Could not clear the Omi cloud session",
         [NSError errorWithDomain:NSOSStatusErrorDomain code:status userInfo:nil]);
}

@end
