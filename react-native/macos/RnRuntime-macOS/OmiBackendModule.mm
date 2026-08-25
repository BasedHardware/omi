#import "OmiBackendModule.h"

#import <LocalAuthentication/LocalAuthentication.h>
#import <Security/Security.h>

static NSString *const OmiContractVersion = @"1.0.0";
static NSString *const OmiDevelopmentBackendUnsupportedBody = @"{\"error\":{\"code\":\"development_backend_unsupported\",\"retryable\":false,\"action\":\"none\"}}";

typedef NS_ENUM(NSInteger, OmiBackendCredentialKind) {
  OmiBackendCredentialKindCloud,
  OmiBackendCredentialKindLocal,
  OmiBackendCredentialKindExamplePlatform,
};

@interface OmiBackendPolicy : NSObject
@property(nonatomic, strong) NSURL *url;
@property(nonatomic, copy) NSString *token;
@property(nonatomic, copy) NSString *clientId;
@property(nonatomic) OmiBackendCredentialKind kind;
@end

@implementation OmiBackendPolicy
@end

static BOOL OmiIsLoopbackHost(NSString *host) {
  NSString *normalized = host.lowercaseString;
  return [normalized isEqualToString:@"localhost"] ||
      [normalized isEqualToString:@"127.0.0.1"] ||
      [normalized isEqualToString:@"::1"];
}

static BOOL OmiIsCloudHost(NSString *host) {
  return [host.lowercaseString isEqualToString:@"api.omi.me"];
}

static NSURL *OmiValidatedURL(NSString *value, BOOL requireLoopback) {
  NSURL *url = value.length > 0 ? [NSURL URLWithString:value] : nil;
  NSSet<NSString *> *schemes = [NSSet setWithArray:@[ @"http", @"https" ]];
  BOOL validPath = url.path.length == 0 || [url.path isEqualToString:@"/"];
  if (url == nil || ![schemes containsObject:url.scheme.lowercaseString] ||
      url.host.length == 0 || url.user.length > 0 || url.password.length > 0 ||
      !validPath || url.query.length > 0 || url.fragment.length > 0) {
    return nil;
  }
  if (requireLoopback && !OmiIsLoopbackHost(url.host)) {
    return nil;
  }
  if (!requireLoopback && !OmiIsCloudHost(url.host) && !OmiIsLoopbackHost(url.host)) {
    return nil;
  }
  return url;
}

static NSURL *OmiLocalBaseURL(NSString *value, NSString *developmentBackend) {
  if (developmentBackend.length > 0) {
#if DEBUG
    if (value.length > 0 || ![developmentBackend isEqualToString:@"example-platform"]) return nil;
    return [NSURL URLWithString:@"http://127.0.0.1:4851"];
#else
    return nil;
#endif
  }
  return OmiValidatedURL(value.length > 0 ? value : @"http://127.0.0.1:8787", YES);
}

static NSDictionary *OmiOwnKeychainCloudSession(void) {
  LAContext *context = [[LAContext alloc] init];
  context.interactionNotAllowed = YES;
  NSDictionary *query = @{
    (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService : @"com.omi.rnruntime.firebase-rest-session",
    (__bridge id)kSecAttrAccount : @"firebase-rest-tokens",
    (__bridge id)kSecReturnData : @YES,
    (__bridge id)kSecMatchLimit : (__bridge id)kSecMatchLimitOne,
    (__bridge id)kSecUseAuthenticationUI : (__bridge id)kSecUseAuthenticationUIFail,
    (__bridge id)kSecUseAuthenticationContext : context,
  };
  CFTypeRef result = NULL;
  OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
  if (status != errSecSuccess || result == NULL) return nil;
  NSData *data = CFBridgingRelease(result);
  id session = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [session isKindOfClass:NSDictionary.class] ? session : nil;
}

static BOOL OmiStoreOwnKeychainCloudSession(NSDictionary *session) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:session options:0 error:nil];
  if (data == nil) return NO;
  NSDictionary *query = @{
    (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService : @"com.omi.rnruntime.firebase-rest-session",
    (__bridge id)kSecAttrAccount : @"firebase-rest-tokens",
  };
  NSDictionary *attributes = @{
    (__bridge id)kSecValueData : data,
    (__bridge id)kSecAttrAccessible : (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
  };
  OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query,
                                  (__bridge CFDictionaryRef)attributes);
  if (status == errSecItemNotFound) {
    NSMutableDictionary *add = [query mutableCopy];
    [add addEntriesFromDictionary:attributes];
    status = SecItemAdd((__bridge CFDictionaryRef)add, NULL);
  }
  return status == errSecSuccess;
}

static void OmiClearOwnKeychainCloudSession(void) {
  NSDictionary *query = @{
    (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService : @"com.omi.rnruntime.firebase-rest-session",
    (__bridge id)kSecAttrAccount : @"firebase-rest-tokens",
  };
  SecItemDelete((__bridge CFDictionaryRef)query);
}

static NSString *OmiOwnKeychainCloudToken(NSDictionary *session) {
  NSString *token = [session[@"idToken"] isKindOfClass:NSString.class] ? session[@"idToken"] : nil;
  NSNumber *expiryTime = [session[@"expiryTime"] isKindOfClass:NSNumber.class] ? session[@"expiryTime"] : nil;
  if (expiryTime != nil && expiryTime.doubleValue <= NSDate.date.timeIntervalSince1970 + 60) return nil;
  return token.length > 0 ? token : nil;
}

static BOOL OmiCloudSessionNeedsRefresh(NSDictionary *session) {
  NSString *token = [session[@"idToken"] isKindOfClass:NSString.class] ? session[@"idToken"] : nil;
  NSNumber *expiryTime = [session[@"expiryTime"] isKindOfClass:NSNumber.class] ? session[@"expiryTime"] : nil;
  return token.length > 0 && expiryTime != nil &&
      expiryTime.doubleValue <= NSDate.date.timeIntervalSince1970 + 60;
}

static BOOL OmiCloudRefreshFailureIsDefinitive(NSDictionary *json) {
  NSDictionary *error = [json[@"error"] isKindOfClass:NSDictionary.class] ? json[@"error"] : nil;
  NSString *message = [error[@"message"] isKindOfClass:NSString.class] ? error[@"message"] : nil;
  NSSet<NSString *> *failures = [NSSet setWithArray:@[
    @"INVALID_REFRESH_TOKEN", @"TOKEN_EXPIRED", @"USER_DISABLED", @"USER_NOT_FOUND"
  ]];
  return [failures containsObject:message];
}

static void OmiRefreshOwnKeychainCloudSession(
    NSDictionary *session,
    NSURLSession *networkSession,
    void (^completion)(NSError *error)) {
  NSString *refreshToken = [session[@"refreshToken"] isKindOfClass:NSString.class]
      ? session[@"refreshToken"] : nil;
  if (refreshToken.length == 0) {
    OmiClearOwnKeychainCloudSession();
    completion(nil);
    return;
  }
  void (^refreshWithKey)(NSString *) = ^(NSString *firebaseApiKey) {
    if (firebaseApiKey.length == 0) {
      completion([NSError errorWithDomain:@"OmiBackend" code:0 userInfo:nil]);
      return;
    }
    NSURLComponents *components = [NSURLComponents componentsWithString:
        @"https://securetoken.googleapis.com/v1/token"];
    components.queryItems = @[[NSURLQueryItem queryItemWithName:@"key" value:firebaseApiKey]];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:components.URL];
    request.HTTPMethod = @"POST";
    [request setValue:@"application/x-www-form-urlencoded" forHTTPHeaderField:@"content-type"];
    NSURLComponents *form = [[NSURLComponents alloc] init];
    form.queryItems = @[
      [NSURLQueryItem queryItemWithName:@"grant_type" value:@"refresh_token"],
      [NSURLQueryItem queryItemWithName:@"refresh_token" value:refreshToken],
    ];
    request.HTTPBody = [form.percentEncodedQuery dataUsingEncoding:NSUTF8StringEncoding];
    [[networkSession dataTaskWithRequest:request
                       completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
      NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
          ? ((NSHTTPURLResponse *)response).statusCode : 0;
      NSDictionary *json = data == nil ? nil
          : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
      if (error != nil || status < 200 || status >= 300 || ![json isKindOfClass:NSDictionary.class]) {
        if (OmiCloudRefreshFailureIsDefinitive(json)) OmiClearOwnKeychainCloudSession();
        completion(error ?: [NSError errorWithDomain:@"OmiBackend" code:status userInfo:nil]);
        return;
      }
      NSString *idToken = [json[@"id_token"] isKindOfClass:NSString.class] ? json[@"id_token"] : nil;
      NSString *newRefreshToken = [json[@"refresh_token"] isKindOfClass:NSString.class]
          ? json[@"refresh_token"] : refreshToken;
      NSNumber *expiresIn = [json[@"expires_in"] respondsToSelector:@selector(doubleValue)]
          ? @([json[@"expires_in"] doubleValue]) : @3600;
      if (idToken.length == 0 || newRefreshToken.length == 0) {
        completion([NSError errorWithDomain:@"OmiBackend" code:status userInfo:nil]);
        return;
      }
      NSMutableDictionary *updated = [session mutableCopy];
      updated[@"idToken"] = idToken;
      updated[@"refreshToken"] = newRefreshToken;
      updated[@"expiryTime"] = @(NSDate.date.timeIntervalSince1970 + MAX(expiresIn.doubleValue, 60));
      updated[@"firebaseApiKey"] = firebaseApiKey;
      NSString *userId = [json[@"user_id"] isKindOfClass:NSString.class] ? json[@"user_id"] : nil;
      if (userId.length > 0) updated[@"tokenUserId"] = userId;
      if (!OmiStoreOwnKeychainCloudSession(updated)) {
        completion([NSError errorWithDomain:@"OmiBackend" code:0 userInfo:nil]);
        return;
      }
      completion(nil);
    }] resume];
  };
  NSString *firebaseApiKey = [session[@"firebaseApiKey"] isKindOfClass:NSString.class]
      ? session[@"firebaseApiKey"] : nil;
  if (firebaseApiKey.length > 0) {
    refreshWithKey(firebaseApiKey);
    return;
  }
  NSMutableURLRequest *configuration = [NSMutableURLRequest requestWithURL:
      [NSURL URLWithString:@"https://api.omi.me/v1/config/api-keys"]];
  [[networkSession dataTaskWithRequest:configuration
                     completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
        ? ((NSHTTPURLResponse *)response).statusCode : 0;
    NSDictionary *json = data == nil ? nil
        : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    NSString *key = [json[@"firebase_api_key"] isKindOfClass:NSString.class]
        ? json[@"firebase_api_key"] : json[@"firebaseApiKey"];
    if (error != nil || status < 200 || status >= 300 || key.length == 0) {
      completion(error ?: [NSError errorWithDomain:@"OmiBackend" code:status userInfo:nil]);
      return;
    }
    refreshWithKey(key);
  }] resume];
}

static OmiBackendPolicy *OmiResolvedBackendPolicy(NSDictionary<NSString *, NSString *> *environment) {
  NSString *developmentBackend = environment[@"OMI_DEV_BACKEND"];
  NSString *localURL = environment[@"OMI_LOCAL_BACKEND_URL"];
  NSString *localToken = environment[@"OMI_LOCAL_API_TOKEN"];
  NSString *localClient = environment[@"OMI_LOCAL_API_CLIENT_ID"];
  BOOL localSelected = developmentBackend.length > 0 || localURL.length > 0 ||
      localToken.length > 0 || localClient.length > 0;
  if (localSelected) {
    if (localToken.length > 0 && localClient.length > 0) {
      NSURL *url = OmiLocalBaseURL(localURL, developmentBackend);
      if (url == nil) return nil;
      OmiBackendPolicy *policy = [[OmiBackendPolicy alloc] init];
      policy.url = url;
      policy.token = [localToken copy];
      policy.clientId = [localClient copy];
      policy.kind = developmentBackend.length > 0
          ? OmiBackendCredentialKindExamplePlatform : OmiBackendCredentialKindLocal;
      return policy;
    }
    return nil;
  }
  NSDictionary *session = OmiOwnKeychainCloudSession();
  NSString *ownKeychainToken = OmiOwnKeychainCloudToken(session);
  NSString *cloud = ownKeychainToken;
  if (cloud.length == 0) cloud = environment[@"OMI_CLOUD_API_TOKEN"] ?: environment[@"OMI_API_TOKEN"];
  if (cloud.length == 0) return nil;
  OmiBackendPolicy *policy = [[OmiBackendPolicy alloc] init];
  policy.url = OmiValidatedURL(@"https://api.omi.me", NO);
  policy.token = [cloud copy];
  policy.clientId = @"omi-macos";
  policy.kind = OmiBackendCredentialKindCloud;
  return policy;
}

static BOOL OmiBackendPolicyIsValid(OmiBackendPolicy *policy) {
  if (policy == nil || policy.url == nil || policy.token.length == 0) return NO;
  NSString *scheme = policy.url.scheme.lowercaseString;
  if (policy.kind == OmiBackendCredentialKindCloud) {
    NSInteger port = policy.url.port != nil ? policy.url.port.integerValue : 443;
    return [scheme isEqualToString:@"https"] && OmiIsCloudHost(policy.url.host) && port == 443;
  }
  return ([scheme isEqualToString:@"http"] || [scheme isEqualToString:@"https"]) &&
      OmiIsLoopbackHost(policy.url.host) && policy.clientId.length > 0;
}

static BOOL OmiApplyAuthorization(NSMutableURLRequest *request, OmiBackendPolicy *policy) {
  if (!OmiBackendPolicyIsValid(policy)) return NO;
  [request setValue:[NSString stringWithFormat:@"Bearer %@", policy.token]
      forHTTPHeaderField:@"authorization"];
  if (policy.kind != OmiBackendCredentialKindCloud) {
    [request setValue:policy.clientId forHTTPHeaderField:@"x-omi-client-id"];
  }
  return YES;
}

static BOOL OmiExamplePlatformRequestSupported(NSString *method, NSString *path) {
  if (![method isEqualToString:@"GET"]) return NO;
  NSURLComponents *components = [NSURLComponents componentsWithString:path];
  NSString *route = components.path;
  return [route isEqualToString:@"/v1/conversations"] ||
      [route isEqualToString:@"/v1/memories"];
}

static NSDictionary *OmiDevelopmentBackendUnsupportedResponse(NSString *requestId) {
  return @{
    @"id": requestId,
    @"status": @503,
    @"body": OmiDevelopmentBackendUnsupportedBody,
    @"retryAfterSeconds": NSNull.null,
  };
}

@interface OmiGenerationDelegate : NSObject <NSURLSessionDataDelegate, NSURLSessionTaskDelegate>
@property(nonatomic, strong) NSMutableData *data;
@property(nonatomic, strong) NSURLSession *session;
@property(nonatomic, strong) NSURLSessionDataTask *task;
@property(nonatomic, strong) NSMutableURLRequest *request;
@property(nonatomic, copy) RCTPromiseResolveBlock resolve;
@property(nonatomic, copy) RCTPromiseRejectBlock reject;
@property(nonatomic, copy) dispatch_block_t cleanup;
@property(nonatomic) BOOL settled;
@property(nonatomic) NSUInteger reconnects;
@property(nonatomic, copy) NSString *lastEventId;
@property(nonatomic, copy) dispatch_block_t reconnectWork;
@property(nonatomic) NSInteger responseStatus;
@property(nonatomic) NSInteger retryAfterSeconds;
@property(nonatomic, copy) NSString *requestId;
- (instancetype)initWithResolve:(RCTPromiseResolveBlock)resolve
                          reject:(RCTPromiseRejectBlock)reject
                         cleanup:(dispatch_block_t)cleanup;
- (void)cancel;
- (void)start;
@end

@implementation OmiGenerationDelegate

- (instancetype)initWithResolve:(RCTPromiseResolveBlock)resolve
                          reject:(RCTPromiseRejectBlock)reject
                         cleanup:(dispatch_block_t)cleanup {
  self = [super init];
  if (self) {
    _data = [NSMutableData data];
    _resolve = [resolve copy];
    _reject = [reject copy];
    _cleanup = [cleanup copy];
  }
  return self;
}

- (void)finishWithValue:(NSString *)value code:(NSString *)code message:(NSString *)message {
  @synchronized(self) {
    if (self.settled) return;
    self.settled = YES;
  }
  if (self.reconnectWork != nil) dispatch_block_cancel(self.reconnectWork);
  if (value != nil) self.resolve(@{
    @"id": self.requestId,
    @"status": @(self.responseStatus),
    @"body": value,
    @"retryAfterSeconds": self.retryAfterSeconds > 0 ? @(self.retryAfterSeconds) : NSNull.null,
  });
  else self.reject(code, message, nil);
  [self.task cancel];
  [self.session finishTasksAndInvalidate];
  self.cleanup();
}

- (void)cancel {
  [self finishWithValue:nil code:@"OMI_HTTP_CANCELLED" message:@"Native generation request was cancelled"];
}

- (void)start {
  self.task = [self.session dataTaskWithRequest:self.request];
  [self.task resume];
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request
 completionHandler:(void (^)(NSURLRequest * _Nullable))completionHandler {
  completionHandler(nil);
}

- (void)URLSession:(NSURLSession *)session
          dataTask:(NSURLSessionDataTask *)dataTask
didReceiveResponse:(NSURLResponse *)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition disposition))completionHandler {
  NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
      ? ((NSHTTPURLResponse *)response).statusCode : 0;
  self.responseStatus = status;
  if ([response isKindOfClass:NSHTTPURLResponse.class]) {
    NSString *retryAfter = [(NSHTTPURLResponse *)response valueForHTTPHeaderField:@"Retry-After"];
    NSInteger parsed = retryAfter.integerValue;
    if (parsed > 0 && parsed <= 3600) self.retryAfterSeconds = parsed;
  }
  completionHandler(NSURLSessionResponseAllow);
}

- (void)URLSession:(NSURLSession *)session
          dataTask:(NSURLSessionDataTask *)dataTask
    didReceiveData:(NSData *)data {
  [self.data appendData:data];
  NSString *text = [[NSString alloc] initWithData:self.data encoding:NSUTF8StringEncoding];
  if (text == nil) return;
  NSArray<NSString *> *blocks = [text componentsSeparatedByString:@"\n\n"];
  for (NSUInteger index = 0; index + 1 < blocks.count; index += 1) {
    NSMutableArray<NSString *> *parts = [NSMutableArray array];
    NSString *eventId = nil;
    for (NSString *line in [blocks[index] componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
      if ([line hasPrefix:@"id:"]) {
        NSString *candidate = [line substringFromIndex:3];
        eventId = [candidate hasPrefix:@" "] ? [candidate substringFromIndex:1] : candidate;
      }
      if ([line hasPrefix:@"data:"]) {
        NSString *part = [line substringFromIndex:5];
        [parts addObject:[part hasPrefix:@" "] ? [part substringFromIndex:1] : part];
      }
    }
    if (parts.count == 0) continue;
    if (eventId.length > 0) self.lastEventId = eventId;
    NSData *jsonData = [[parts componentsJoinedByString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *frame = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:nil];
    NSString *kind = [frame[@"kind"] isKindOfClass:NSString.class] ? frame[@"kind"] : nil;
    if ([kind isEqualToString:@"done"] || [kind isEqualToString:@"failed"] ||
        [kind isEqualToString:@"cancelled"]) {
      [self finishWithValue:[blocks[index] stringByAppendingString:@"\n\n"] code:nil message:nil];
      return;
    }
  }
  NSData *remaining = [blocks.lastObject dataUsingEncoding:NSUTF8StringEncoding];
  [self.data setData:remaining ?: [NSData data]];
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
didCompleteWithError:(NSError *)error {
  @synchronized(self) {
    if (self.settled) return;
  }
  if (self.responseStatus != 0 && self.responseStatus != 200) {
    NSString *body = [[NSString alloc] initWithData:self.data encoding:NSUTF8StringEncoding];
    [self finishWithValue:body ?: @"" code:nil message:nil];
    return;
  }
  if (self.reconnects < 5) {
    NSTimeInterval delay = 0.25 * (1 << self.reconnects);
    self.reconnects += 1;
    [self.data setLength:0];
    if (self.lastEventId.length > 0) {
      [self.request setValue:self.lastEventId forHTTPHeaderField:@"last-event-id"];
    }
    __weak OmiGenerationDelegate *weakSelf = self;
    dispatch_block_t reconnect = dispatch_block_create(DISPATCH_BLOCK_INHERIT_QOS_CLASS, ^{
      OmiGenerationDelegate *strongSelf = weakSelf;
      if (strongSelf == nil) return;
      @synchronized(strongSelf) {
        if (strongSelf.settled) return;
      }
      [strongSelf start];
    });
    self.reconnectWork = reconnect;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
                   dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), reconnect);
    return;
  }
  NSString *message = self.responseStatus == 0
      ? @"Native generation transport failed before an HTTP response"
      : @"Generation ended without a terminal frame";
  [self finishWithValue:nil code:@"OMI_HTTP_TRANSPORT" message:message];
}

@end

@interface OmiBackendModule () <NSURLSessionTaskDelegate>
@property(nonatomic, strong) NSURLSession *session;
@property(nonatomic, strong) OmiBackendPolicy *policy;
@property(nonatomic, strong) NSMutableDictionary<NSString *, OmiGenerationDelegate *> *generations;
@end

@implementation OmiBackendModule

RCT_EXPORT_MODULE(OmiBackend)

+ (BOOL)requiresMainQueueSetup {
  return NO;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    NSDictionary<NSString *, NSString *> *environment = NSProcessInfo.processInfo.environment;
    _policy = OmiResolvedBackendPolicy(environment);
    _generations = [NSMutableDictionary dictionary];
    NSURLSessionConfiguration *configuration = [NSURLSessionConfiguration ephemeralSessionConfiguration];
    configuration.timeoutIntervalForRequest = 10;
    configuration.timeoutIntervalForResource = 15;
    configuration.HTTPCookieStorage = nil;
    configuration.HTTPShouldSetCookies = NO;
    configuration.HTTPCookieAcceptPolicy = NSHTTPCookieAcceptPolicyNever;
    _session = [NSURLSession sessionWithConfiguration:configuration delegate:self delegateQueue:nil];
  }
  return self;
}

- (BOOL)examplePlatformBackend {
  return self.policy.kind == OmiBackendCredentialKindExamplePlatform;
}

- (void)resolveBackendPolicyWithCompletion:(void (^)(OmiBackendPolicy *, NSError *))completion {
  NSDictionary<NSString *, NSString *> *environment = NSProcessInfo.processInfo.environment;
  BOOL localSelected = [environment[@"OMI_DEV_BACKEND"] length] > 0 ||
      [environment[@"OMI_LOCAL_BACKEND_URL"] length] > 0 ||
      [environment[@"OMI_LOCAL_API_TOKEN"] length] > 0 ||
      [environment[@"OMI_LOCAL_API_CLIENT_ID"] length] > 0;
  if (localSelected) {
    self.policy = OmiResolvedBackendPolicy(environment);
    completion(self.policy, nil);
    return;
  }
  NSDictionary *session = OmiOwnKeychainCloudSession();
  if (!OmiCloudSessionNeedsRefresh(session)) {
    self.policy = OmiResolvedBackendPolicy(environment);
    completion(self.policy, nil);
    return;
  }
  OmiRefreshOwnKeychainCloudSession(session, self.session, ^(NSError *error) {
    self.policy = OmiResolvedBackendPolicy(environment);
    BOOL sessionCleared = OmiOwnKeychainCloudSession() == nil;
    completion(self.policy, sessionCleared ? nil : error);
  });
}

RCT_REMAP_METHOD(request,
                 requestWithValue:(NSDictionary *)value
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self resolveBackendPolicyWithCompletion:^(OmiBackendPolicy *policy, NSError *resolutionError) {
  if (resolutionError != nil && policy == nil) {
    reject(@"OMI_HTTP_TRANSPORT", @"Native HTTP session refresh failed", nil);
    return;
  }
  NSString *requestId = [value[@"id"] isKindOfClass:NSString.class] ? value[@"id"] : nil;
  NSString *method = [value[@"method"] isKindOfClass:NSString.class] ? value[@"method"] : nil;
  NSString *path = [value[@"path"] isKindOfClass:NSString.class] ? value[@"path"] : nil;
  NSDictionary *headers = [value[@"headers"] isKindOfClass:NSDictionary.class] ? value[@"headers"] : @{};
  NSString *body = [value[@"body"] isKindOfClass:NSString.class] ? value[@"body"] : nil;
  NSSet<NSString *> *methods = [NSSet setWithArray:@[ @"GET", @"POST", @"PATCH", @"DELETE" ]];
  NSSet<NSString *> *schemes = [NSSet setWithArray:@[ @"http", @"https" ]];
  if (requestId.length == 0 || ![methods containsObject:method] || ![path hasPrefix:@"/"] ||
      [path hasPrefix:@"//"] || [path containsString:@"://"]) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native HTTP request is invalid", nil);
    return;
  }
  if (!OmiBackendPolicyIsValid(policy) ||
      ![schemes containsObject:policy.url.scheme.lowercaseString]) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native HTTP configuration is unavailable", nil);
    return;
  }
  if (self.examplePlatformBackend && !OmiExamplePlatformRequestSupported(method, path)) {
    resolve(OmiDevelopmentBackendUnsupportedResponse(requestId));
    return;
  }
  NSURL *url = [NSURL URLWithString:path relativeToURL:policy.url].absoluteURL;
  NSInteger basePort = policy.url.port != nil
      ? policy.url.port.integerValue
      : ([policy.url.scheme.lowercaseString isEqualToString:@"https"] ? 443 : 80);
  NSInteger requestPort = url.port != nil
      ? url.port.integerValue
      : ([url.scheme.lowercaseString isEqualToString:@"https"] ? 443 : 80);
  BOOL schemeMatches = url != nil && [url.scheme caseInsensitiveCompare:policy.url.scheme] == NSOrderedSame;
  BOOL hostMatches = url != nil && [url.host caseInsensitiveCompare:policy.url.host] == NSOrderedSame;
  BOOL portMatches = url != nil && requestPort == basePort;
  if (!schemeMatches || !hostMatches || !portMatches) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native HTTP request is unavailable or invalid", nil);
    return;
  }
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.HTTPMethod = method;
  NSSet<NSString *> *forbidden = [NSSet setWithArray:@[
    @"authorization", @"cookie", @"proxy-authorization", @"x-omi-contract-version", @"x-omi-client-id"
  ]];
  for (id rawName in headers) {
    id rawValue = headers[rawName];
    if (![rawName isKindOfClass:NSString.class] || ![rawValue isKindOfClass:NSString.class] ||
        [forbidden containsObject:[rawName lowercaseString]]) {
      continue;
    }
    [request setValue:rawValue forHTTPHeaderField:rawName];
  }
  if (body != nil) {
    request.HTTPBody = [body dataUsingEncoding:NSUTF8StringEncoding];
    [request setValue:@"application/json" forHTTPHeaderField:@"content-type"];
  }
  if (!OmiApplyAuthorization(request, policy)) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native HTTP configuration is unavailable", nil);
    return;
  }
  [request setValue:OmiContractVersion forHTTPHeaderField:@"x-omi-contract-version"];
  NSURLSessionDataTask *task = [self.session dataTaskWithRequest:request
                                              completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    if (error != nil) {
      reject(@"OMI_HTTP_TRANSPORT", @"Native HTTP transport failed", nil);
      return;
    }
    if (![response isKindOfClass:NSHTTPURLResponse.class]) {
      reject(@"OMI_HTTP_TRANSPORT", @"Native HTTP transport failed", nil);
      return;
    }
    NSHTTPURLResponse *httpResponse = (NSHTTPURLResponse *)response;
    NSString *retryAfter = [httpResponse valueForHTTPHeaderField:@"Retry-After"];
    NSInteger retryAfterSeconds = retryAfter.integerValue;
    NSString *responseBody = data.length > 0 ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
    if (data.length > 0 && responseBody == nil) {
      reject(@"OMI_HTTP_TRANSPORT", @"Native HTTP response was not UTF-8", nil);
      return;
    }
    resolve(@{
      @"id": requestId,
      @"status": @(httpResponse.statusCode),
      @"body": responseBody ?: NSNull.null,
      @"retryAfterSeconds": retryAfterSeconds > 0 && retryAfterSeconds <= 3600
          ? @(retryAfterSeconds) : NSNull.null,
    });
  }];
  [task resume];
  }];
}

RCT_REMAP_METHOD(generationEvents,
                 generationEventsWithId:(NSString *)generationId
                 lastEventId:(NSString *)lastEventId
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self resolveBackendPolicyWithCompletion:^(OmiBackendPolicy *policy, NSError *resolutionError) {
  if (resolutionError != nil && policy == nil) {
    reject(@"OMI_HTTP_TRANSPORT", @"Native generation session refresh failed", nil);
    return;
  }
  NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"];
  NSString *encoded = [generationId stringByAddingPercentEncodingWithAllowedCharacters:allowed];
  if (generationId.length == 0 || generationId.length > 256 || encoded.length == 0 ||
      (lastEventId != nil && (lastEventId.length == 0 || lastEventId.length > 1024))) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native generation request is invalid", nil);
    return;
  }
  if (self.examplePlatformBackend) {
    resolve(OmiDevelopmentBackendUnsupportedResponse(generationId));
    return;
  }
  NSString *path = [NSString stringWithFormat:@"/v1/chat-generations/%@/events", encoded];
  NSURL *url = [NSURL URLWithString:path relativeToURL:policy.url].absoluteURL;
  if (url == nil || !OmiBackendPolicyIsValid(policy)) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native generation request is unavailable", nil);
    return;
  }
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.HTTPMethod = @"GET";
  if (!OmiApplyAuthorization(request, policy)) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native generation request is unavailable", nil);
    return;
  }
  [request setValue:OmiContractVersion forHTTPHeaderField:@"x-omi-contract-version"];
  [request setValue:@"text/event-stream" forHTTPHeaderField:@"accept"];
  [request setValue:@"no-cache" forHTTPHeaderField:@"cache-control"];
  if (lastEventId != nil) [request setValue:lastEventId forHTTPHeaderField:@"last-event-id"];
  @synchronized(self.generations) {
    if (self.generations[generationId] != nil) {
      reject(@"OMI_HTTP_INVALID_REQUEST", @"Generation request is already active", nil);
      return;
    }
  }
  __weak OmiBackendModule *weakSelf = self;
  OmiGenerationDelegate *delegate = [[OmiGenerationDelegate alloc]
      initWithResolve:resolve reject:reject cleanup:^{
        OmiBackendModule *strongSelf = weakSelf;
        if (strongSelf == nil) return;
        @synchronized(strongSelf.generations) {
          [strongSelf.generations removeObjectForKey:generationId];
        }
      }];
  NSURLSessionConfiguration *configuration = [NSURLSessionConfiguration ephemeralSessionConfiguration];
  configuration.timeoutIntervalForRequest = 30;
  configuration.timeoutIntervalForResource = 60 * 60;
  configuration.HTTPCookieStorage = nil;
  configuration.HTTPShouldSetCookies = NO;
  configuration.HTTPCookieAcceptPolicy = NSHTTPCookieAcceptPolicyNever;
  NSOperationQueue *queue = [[NSOperationQueue alloc] init];
  queue.maxConcurrentOperationCount = 1;
  delegate.session = [NSURLSession sessionWithConfiguration:configuration delegate:delegate delegateQueue:queue];
  delegate.request = request;
  delegate.requestId = generationId;
  @synchronized(self.generations) {
    self.generations[generationId] = delegate;
  }
  [delegate start];
  }];
}

RCT_REMAP_METHOD(cancelGenerationEvents,
                 cancelGenerationEventsWithId:(NSString *)generationId
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self resolveBackendPolicyWithCompletion:^(OmiBackendPolicy *policy, NSError *resolutionError) {
  if (resolutionError != nil && policy == nil) {
    reject(@"OMI_HTTP_TRANSPORT", @"Native generation session refresh failed", nil);
    return;
  }
  if (self.examplePlatformBackend) {
    reject(@"OMI_DEV_BACKEND_UNSUPPORTED", @"Generation cancellation is unsupported by the selected development backend", nil);
    return;
  }
  OmiGenerationDelegate *delegate;
  @synchronized(self.generations) {
    delegate = self.generations[generationId];
  }
  NSString *encoded = [generationId stringByAddingPercentEncodingWithAllowedCharacters:
      [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"]];
  if (generationId.length == 0 || generationId.length > 256 || encoded.length == 0) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native generation cancellation is invalid", nil);
    return;
  }
  if (!OmiBackendPolicyIsValid(policy)) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native generation cancellation is unavailable", nil);
    return;
  }
  NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"/v1/chat-generations/%@", encoded]
                     relativeToURL:policy.url].absoluteURL;
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.HTTPMethod = @"DELETE";
  if (!OmiApplyAuthorization(request, policy)) {
    reject(@"OMI_HTTP_UNCONFIGURED", @"Native generation cancellation is unavailable", nil);
    return;
  }
  [request setValue:OmiContractVersion forHTTPHeaderField:@"x-omi-contract-version"];
  NSURLSessionDataTask *task = [self.session dataTaskWithRequest:request
                                              completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class]
        ? ((NSHTTPURLResponse *)response).statusCode : 0;
    if (error != nil || (status != 202 && status != 204)) {
      reject(@"OMI_HTTP_TRANSPORT", @"Generation cancellation was not accepted", nil);
      return;
    }
    if (delegate != nil) [delegate cancel];
    resolve(nil);
  }];
  [task resume];
  }];
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request
 completionHandler:(void (^)(NSURLRequest * _Nullable))completionHandler {
  completionHandler(nil);
}

@end
