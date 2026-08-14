#import "OmiBackendModule.h"

static NSString *const OmiContractVersion = @"1.0.0";

@interface OmiGenerationDelegate : NSObject <NSURLSessionDataDelegate, NSURLSessionTaskDelegate>
@property(nonatomic, strong) NSMutableData *data;
@property(nonatomic, strong) NSURLSession *session;
@property(nonatomic, strong) NSURLSessionDataTask *task;
@property(nonatomic, copy) RCTPromiseResolveBlock resolve;
@property(nonatomic, copy) RCTPromiseRejectBlock reject;
@property(nonatomic, copy) dispatch_block_t cleanup;
@property(nonatomic) BOOL settled;
- (instancetype)initWithResolve:(RCTPromiseResolveBlock)resolve
                          reject:(RCTPromiseRejectBlock)reject
                         cleanup:(dispatch_block_t)cleanup;
- (void)cancel;
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
  if (value != nil) self.resolve(value);
  else self.reject(code, message, nil);
  [self.task cancel];
  [self.session finishTasksAndInvalidate];
  self.cleanup();
}

- (void)cancel {
  [self finishWithValue:nil code:@"OMI_HTTP_CANCELLED" message:@"Native generation request was cancelled"];
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
  if (![response isKindOfClass:NSHTTPURLResponse.class] ||
      ((NSHTTPURLResponse *)response).statusCode != 200) {
    completionHandler(NSURLSessionResponseCancel);
    [self finishWithValue:nil code:@"OMI_HTTP_TRANSPORT" message:@"Native generation transport failed"];
    return;
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
    for (NSString *line in [blocks[index] componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
      if ([line hasPrefix:@"data:"]) {
        NSString *part = [line substringFromIndex:5];
        [parts addObject:[part hasPrefix:@" "] ? [part substringFromIndex:1] : part];
      }
    }
    if (parts.count == 0) continue;
    NSData *jsonData = [[parts componentsJoinedByString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *frame = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:nil];
    NSString *kind = [frame[@"kind"] isKindOfClass:NSString.class] ? frame[@"kind"] : nil;
    if ([kind isEqualToString:@"done"] || [kind isEqualToString:@"failed"] ||
        [kind isEqualToString:@"cancelled"]) {
      NSRange end = [text rangeOfString:@"\n\n" options:0 range:NSMakeRange(0, text.length)];
      NSUInteger terminalEnd = 0;
      for (NSUInteger blockIndex = 0; blockIndex <= index; blockIndex += 1) {
        NSRange boundary = [text rangeOfString:@"\n\n" options:0 range:NSMakeRange(terminalEnd, text.length - terminalEnd)];
        if (boundary.location == NSNotFound) break;
        terminalEnd = NSMaxRange(boundary);
      }
      if (end.location != NSNotFound && terminalEnd > 0) {
        [self finishWithValue:[text substringToIndex:terminalEnd] code:nil message:nil];
      }
      return;
    }
  }
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
didCompleteWithError:(NSError *)error {
  @synchronized(self) {
    if (self.settled) return;
  }
  [self finishWithValue:nil code:@"OMI_HTTP_TRANSPORT" message:@"Generation ended without a terminal frame"];
}

@end

@interface OmiBackendModule () <NSURLSessionTaskDelegate>
@property(nonatomic, strong) NSURLSession *session;
@property(nonatomic, strong) NSURL *baseURL;
@property(nonatomic, copy) NSString *token;
@property(nonatomic, copy) NSString *clientId;
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
    NSString *baseURL = environment[@"OMI_API_BASE_URL"];
    _baseURL = baseURL.length > 0 ? [NSURL URLWithString:baseURL] : nil;
    _token = [environment[@"OMI_API_TOKEN"] copy];
    _clientId = [environment[@"OMI_API_CLIENT_ID"] copy];
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

RCT_REMAP_METHOD(request,
                 requestWithValue:(NSDictionary *)value
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSString *requestId = [value[@"id"] isKindOfClass:NSString.class] ? value[@"id"] : nil;
  NSString *method = [value[@"method"] isKindOfClass:NSString.class] ? value[@"method"] : nil;
  NSString *path = [value[@"path"] isKindOfClass:NSString.class] ? value[@"path"] : nil;
  NSDictionary *headers = [value[@"headers"] isKindOfClass:NSDictionary.class] ? value[@"headers"] : @{};
  NSString *body = [value[@"body"] isKindOfClass:NSString.class] ? value[@"body"] : nil;
  NSSet<NSString *> *methods = [NSSet setWithArray:@[ @"GET", @"POST", @"PATCH", @"DELETE" ]];
  NSSet<NSString *> *schemes = [NSSet setWithArray:@[ @"http", @"https" ]];
  if (requestId.length == 0 || ![methods containsObject:method] || ![path hasPrefix:@"/"] ||
      [path hasPrefix:@"//"] || [path containsString:@"://"] || self.baseURL == nil ||
      ![schemes containsObject:self.baseURL.scheme.lowercaseString] || self.baseURL.host.length == 0 ||
      self.token.length == 0 || self.clientId.length == 0) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native HTTP request is unavailable or invalid", nil);
    return;
  }
  NSURL *url = [NSURL URLWithString:path relativeToURL:self.baseURL].absoluteURL;
  if (url == nil || ![url.scheme isEqualToString:self.baseURL.scheme] ||
      ![url.host isEqualToString:self.baseURL.host] || ![url.port isEqual:self.baseURL.port]) {
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
  [request setValue:[NSString stringWithFormat:@"Bearer %@", self.token]
      forHTTPHeaderField:@"authorization"];
  [request setValue:OmiContractVersion forHTTPHeaderField:@"x-omi-contract-version"];
  [request setValue:self.clientId forHTTPHeaderField:@"x-omi-client-id"];
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
    NSString *responseBody = data.length > 0 ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
    if (data.length > 0 && responseBody == nil) {
      reject(@"OMI_HTTP_TRANSPORT", @"Native HTTP response was not UTF-8", nil);
      return;
    }
    resolve(@{
      @"id": requestId,
      @"status": @(httpResponse.statusCode),
      @"body": responseBody ?: NSNull.null,
    });
  }];
  [task resume];
}

RCT_REMAP_METHOD(generationEvents,
                 generationEventsWithId:(NSString *)generationId
                 lastEventId:(NSString *)lastEventId
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"];
  NSString *encoded = [generationId stringByAddingPercentEncodingWithAllowedCharacters:allowed];
  if (generationId.length == 0 || generationId.length > 256 || encoded.length == 0 ||
      (lastEventId != nil && (lastEventId.length == 0 || lastEventId.length > 1024))) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native generation request is invalid", nil);
    return;
  }
  NSString *path = [NSString stringWithFormat:@"/v1/chat-generations/%@/events", encoded];
  NSURL *url = [NSURL URLWithString:path relativeToURL:self.baseURL].absoluteURL;
  if (url == nil || self.token.length == 0 || self.clientId.length == 0) {
    reject(@"OMI_HTTP_INVALID_REQUEST", @"Native generation request is unavailable", nil);
    return;
  }
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.HTTPMethod = @"GET";
  [request setValue:[NSString stringWithFormat:@"Bearer %@", self.token] forHTTPHeaderField:@"authorization"];
  [request setValue:OmiContractVersion forHTTPHeaderField:@"x-omi-contract-version"];
  [request setValue:self.clientId forHTTPHeaderField:@"x-omi-client-id"];
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
  delegate.task = [delegate.session dataTaskWithRequest:request];
  @synchronized(self.generations) {
    self.generations[generationId] = delegate;
  }
  [delegate.task resume];
}

RCT_REMAP_METHOD(cancelGenerationEvents,
                 cancelGenerationEventsWithId:(NSString *)generationId
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  OmiGenerationDelegate *delegate;
  @synchronized(self.generations) {
    delegate = self.generations[generationId];
  }
  [delegate cancel];
  resolve(nil);
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
willPerformHTTPRedirection:(NSHTTPURLResponse *)response
        newRequest:(NSURLRequest *)request
 completionHandler:(void (^)(NSURLRequest * _Nullable))completionHandler {
  completionHandler(nil);
}

@end
