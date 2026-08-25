#import <AppKit/AppKit.h>
#import <AuthenticationServices/AuthenticationServices.h>
#import <CommonCrypto/CommonDigest.h>
#import <LocalAuthentication/LocalAuthentication.h>
#import <React/RCTBridgeModule.h>
#import <Security/Security.h>
#import <arpa/inet.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <string.h>
#import <unistd.h>

static NSString *const OmiAuthKeychainService = @"com.omi.rnruntime.firebase-rest-session";
static NSString *const OmiAuthKeychainAccount = @"firebase-rest-tokens";
static NSString *const OmiOnboardingCompletedKey = @"omi.onboarding.completed";

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
      listen(fileDescriptor, 1) != 0) {
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

static NSURL *OmiAuthAcceptCallback(int listener, NSTimeInterval timeout) {
  if (listener < 0) return nil;
  fd_set readSet;
  FD_ZERO(&readSet);
  FD_SET(listener, &readSet);
  struct timeval wait = {.tv_sec = (int)timeout, .tv_usec = 0};
  if (select(listener + 1, &readSet, NULL, NULL, &wait) <= 0) return nil;
  int client = accept(listener, NULL, NULL);
  if (client < 0) return nil;
  char buffer[4096];
  ssize_t count = recv(client, buffer, sizeof(buffer) - 1, 0);
  NSString *path = nil;
  if (count > 0) {
    buffer[count] = 0;
    NSString *request = [[NSString alloc] initWithBytes:buffer
                                                 length:(NSUInteger)count
                                               encoding:NSUTF8StringEncoding];
    NSScanner *scanner = [NSScanner scannerWithString:request ?: @""];
    [scanner scanString:@"GET " intoString:NULL];
    [scanner scanUpToString:@" " intoString:&path];
  }
  const char *body =
      "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
      "Connection: close\r\n\r\n"
      "<html><body>Signed in to Omi. You can close this window.</body></html>";
  send(client, body, strlen(body), 0);
  close(client);
  if (path.length == 0) return nil;
  return [NSURL URLWithString:[@"http://127.0.0.1" stringByAppendingString:path]];
}

static NSDictionary *OmiAuthKeychainQuery(void) {
  return @{
    (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService : OmiAuthKeychainService,
    (__bridge id)kSecAttrAccount : OmiAuthKeychainAccount,
  };
}

static NSString *OmiAuthStoredToken(void) {
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
  NSString *token = [session[@"idToken"] isKindOfClass:NSString.class] ? session[@"idToken"] : nil;
  return token.length > 0 ? token : nil;
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

static BOOL OmiAuthStoreSession(NSString *idToken, NSString *refreshToken, NSNumber *expiresIn, NSString *localId) {
  NSDictionary *payload = OmiAuthJWTPayload(idToken);
  NSNumber *expiry = [payload[@"exp"] isKindOfClass:NSNumber.class]
      ? payload[@"exp"]
      : @(NSDate.date.timeIntervalSince1970 + MAX(expiresIn.doubleValue, 3600));
  NSString *userId = localId.length > 0 ? localId
      : ([payload[@"user_id"] isKindOfClass:NSString.class] ? payload[@"user_id"] : payload[@"sub"]);
  NSDictionary *session = @{
    @"idToken" : idToken,
    @"refreshToken" : refreshToken ?: @"",
    @"expiryTime" : expiry,
    @"tokenUserId" : userId ?: @"",
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

@interface OmiAuthModule : NSObject <RCTBridgeModule, ASWebAuthenticationPresentationContextProviding>
@property(nonatomic, strong) ASWebAuthenticationSession *authenticationSession;
@property(nonatomic) int loopbackListener;
@property(nonatomic) BOOL settled;
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

- (void)finishWithTokenResponse:(NSDictionary *)tokenResponse
                         resolve:(RCTPromiseResolveBlock)resolve
                          reject:(RCTPromiseRejectBlock)reject {
  NSString *idToken = [tokenResponse[@"id_token"] isKindOfClass:NSString.class] ? tokenResponse[@"id_token"] : nil;
  if (idToken.length > 0) {
    if (!OmiAuthStoreSession(idToken, @"", @3600, @"")) {
      reject(@"OMI_AUTH_UNCONFIGURED", @"Could not store the Omi cloud session", nil);
      return;
    }
    resolve(@{@"signedIn" : @YES});
    return;
  }
  NSString *customToken = [tokenResponse[@"custom_token"] isKindOfClass:NSString.class]
      ? tokenResponse[@"custom_token"] : nil;
  if (customToken.length == 0) {
    reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud did not return a usable session", nil);
    return;
  }
  NSMutableURLRequest *configuration = [NSMutableURLRequest requestWithURL:
      [NSURL URLWithString:@"https://api.omi.me/v1/config/api-keys"]];
  [configuration setValue:[NSString stringWithFormat:@"Bearer %@", customToken]
       forHTTPHeaderField:@"authorization"];
  [self performRequest:configuration completion:^(NSDictionary *keys, NSError *keysError) {
    NSString *firebaseKey = [keys[@"firebase_api_key"] isKindOfClass:NSString.class]
        ? keys[@"firebase_api_key"] : keys[@"firebaseApiKey"];
    if (keysError != nil || firebaseKey.length == 0) {
      reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud could not establish a Firebase session", keysError);
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
      NSString *firebaseIdToken = [tokens[@"idToken"] isKindOfClass:NSString.class] ? tokens[@"idToken"] : nil;
      if (firebaseError != nil || firebaseIdToken.length == 0 ||
          !OmiAuthStoreSession(firebaseIdToken, tokens[@"refreshToken"], tokens[@"expiresIn"], tokens[@"localId"])) {
        reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud could not establish a Firebase session", firebaseError);
        return;
      }
      resolve(@{@"signedIn" : @YES});
    }];
  }];
}

- (void)completeSignInWithCallback:(NSURL *)callbackURL
                             state:(NSString *)state
                          verifier:(NSString *)verifier
                       redirectURI:(NSString *)redirectURI
                           resolve:(RCTPromiseResolveBlock)resolve
                            reject:(RCTPromiseRejectBlock)reject {
  @synchronized (self) {
    if (self.settled) return;
    self.settled = YES;
  }
  [self.authenticationSession cancel];
  self.authenticationSession = nil;
  [self closeLoopback];
  if (callbackURL == nil) {
    reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud sign in was cancelled or failed", nil);
    return;
  }
  NSURLComponents *callback = [NSURLComponents componentsWithURL:callbackURL resolvingAgainstBaseURL:NO];
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  for (NSURLQueryItem *item in callback.queryItems) if (item.value != nil) values[item.name] = item.value;
  if (![values[@"state"] isEqualToString:state] || values[@"code"].length == 0) {
    reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud sign in callback was invalid", nil);
    return;
  }
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
    if (exchangeError != nil) {
      reject(@"OMI_AUTH_UNAUTHORIZED", @"Omi cloud token exchange failed", exchangeError);
      return;
    }
    [self finishWithTokenResponse:tokens resolve:resolve reject:reject];
  }];
}

RCT_REMAP_METHOD(hasCloudSession,
                 hasCloudSessionWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSDictionary *environment = NSProcessInfo.processInfo.environment;
  BOOL available = OmiAuthStoredToken().length > 0 ||
      [environment[@"OMI_CLOUD_API_TOKEN"] length] > 0 ||
      [environment[@"OMI_API_TOKEN"] length] > 0;
  resolve(@(available));
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
    self.loopbackListener = listener;
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
      NSURL *callbackURL = OmiAuthAcceptCallback(listener, 180);
      dispatch_async(dispatch_get_main_queue(), ^{
        [self completeSignInWithCallback:callbackURL
                                   state:state
                                verifier:verifier
                             redirectURI:redirectURI
                                 resolve:resolve
                                  reject:reject];
      });
    });
    self.authenticationSession = [[ASWebAuthenticationSession alloc]
        initWithURL:authorize.URL callbackURLScheme:@"http"
        completionHandler:^(NSURL *callbackURL, NSError *error) {
      if (error != nil && callbackURL == nil) {
        dispatch_async(dispatch_get_main_queue(), ^{
          [self completeSignInWithCallback:nil
                                     state:state
                                  verifier:verifier
                               redirectURI:redirectURI
                                   resolve:resolve
                                    reject:reject];
        });
        return;
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        [self completeSignInWithCallback:callbackURL
                                   state:state
                                verifier:verifier
                             redirectURI:redirectURI
                                 resolve:resolve
                                  reject:reject];
      });
    }];
    self.authenticationSession.presentationContextProvider = self;
    self.authenticationSession.prefersEphemeralWebBrowserSession = NO;
    if (![self.authenticationSession start]) {
      if (![NSWorkspace.sharedWorkspace openURL:authorize.URL]) {
        [self completeSignInWithCallback:nil
                                   state:state
                                verifier:verifier
                             redirectURI:redirectURI
                                 resolve:resolve
                                  reject:reject];
      }
    }
  });
}

@end
