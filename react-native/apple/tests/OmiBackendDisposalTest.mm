#import "../../macos/RnRuntime-macOS/OmiBackendModule.mm"
#include <cassert>

@implementation RCTEventEmitter
- (void)invalidate {}
- (void)sendEventWithName:(NSString *)name body:(id)body { abort(); }
@end
static BOOL ignoreTestEnvironment = YES;
BOOL OmiAuthEnvironmentCloudTokensIgnored(void) { return ignoreTestEnvironment; }
void OmiAuthSetEnvironmentCloudTokensIgnored(BOOL value) {}
BOOL OmiAuthShippingSessionIgnored(void) { return YES; }
void OmiAuthSetShippingSessionIgnored(BOOL value) {}
BOOL OmiAuthImportShippingSessionIfNeeded(void) { return NO; }
id OmiAuthKeychainLock(void) { return @"disposal-test-lock"; }
NSString *OmiAuthKeychainService(void) { return @"omi-disposal-test-unconfigured"; }
BOOL OmiAuthUsesDataProtectionKeychain(void) { return NO; }
NSString *OmiAuthResolvedFirebaseApiKey(void) { return @""; }

@interface DisposalTask : NSObject
@property(nonatomic) NSUInteger resumes;
- (void)resume;
@end
@implementation DisposalTask
- (void)resume { self.resumes++; }
@end
@interface DisposalSession : NSObject
@property(nonatomic, copy) void (^completion)(NSData *, NSURLResponse *, NSError *);
@property(nonatomic) NSUInteger invalidations;
@property(nonatomic, strong) DisposalTask *task;
- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))completion;
- (void)invalidateAndCancel;
@end
@implementation DisposalSession
- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))completion { self.completion = completion; self.task = [DisposalTask new]; return (NSURLSessionDataTask *)self.task; }
- (void)invalidateAndCancel { self.invalidations++; }
@end

@interface DisposalBackend : OmiBackendModule
@property(nonatomic, copy) void (^pendingOwner)(NSDictionary *);
@end
@implementation DisposalBackend
- (void)ensureRecordingJournals {}
- (void)resolveBackendPolicyWithCompletion:(void (^)(OmiBackendPolicy *, NSError *))completion {
  OmiBackendPolicy *policy = [OmiBackendPolicy new]; policy.url = [NSURL URLWithString:@"http://127.0.0.1:1"]; policy.token = @"synthetic-test"; policy.clientId = @"test"; policy.kind = OmiBackendCredentialKindLocal;
  completion(policy, nil);
}
- (void)recordingOwner:(void (^)(NSDictionary *))completion allowCached:(BOOL)allowCached rejecter:(RCTPromiseRejectBlock)reject { self.pendingOwner = completion; }
@end

@interface DeferredChatBackend : OmiBackendModule
@property(nonatomic, copy) void (^pendingPolicy)(OmiBackendPolicy *, NSError *);
@end
@implementation DeferredChatBackend
- (void)resolveBackendPolicyWithCompletion:(void (^)(OmiBackendPolicy *, NSError *))completion { self.pendingPolicy = completion; }
@end

static void testSelectedContract(void) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  NSDictionary *previous = [defaults volatileDomainForName:NSArgumentDomain];
  @try {
    ignoreTestEnvironment = NO;
    NSDictionary *environment = @{@"OMI_CLOUD_API_TOKEN":@"synthetic-contract-token"};
    [defaults setVolatileDomain:@{OmiSoftwarePlaneDefaultsKey:@"new"} forName:NSArgumentDomain];
    assert(OmiResolvedBackendPolicy(environment) == nil);
    NSMutableDictionary *configured = [environment mutableCopy];
    configured[@"OMI_V5_BACKEND_URL"] = @"https://synthetic.workers.dev";
    assert(OmiResolvedBackendPolicy(configured).captureOriginRequired);
    configured[@"OMI_V5_BACKEND_URL"] = @"https://untrusted.invalid";
    assert(OmiResolvedBackendPolicy(configured) == nil);
    [defaults setVolatileDomain:@{OmiSoftwarePlaneDefaultsKey:@"old"} forName:NSArgumentDomain];
    OmiBackendPolicy *old = OmiResolvedBackendPolicy(environment);
    assert(old != nil && old.kind == OmiBackendCredentialKindCloud && !old.captureOriginRequired);
  } @finally {
    ignoreTestEnvironment = YES;
    [defaults setVolatileDomain:previous forName:NSArgumentDomain];
  }
}

static void testPendingOmiCancellation(void) {
  for (NSNumber *dispose in @[@NO, @YES]) {
    DeferredChatBackend *module = [DeferredChatBackend new];
    __block NSUInteger rejected = 0;
    [module sendOmiChatWithId:@"pending-chat" text:@"Synthetic" resolver:^(id value) { abort(); } rejecter:^(NSString *code, NSString *message, NSError *error) { assert([code isEqual:@"OMI_HTTP_CANCELLED"]); rejected++; }];
    assert(module.generations.count == 1);
    if (dispose.boolValue) [module invalidate];
    else [module cancelOmiChatWithId:@"pending-chat" resolver:^(id value) {} rejecter:^(NSString *code, NSString *message, NSError *error) { abort(); }];
    assert(rejected == 1 && module.generations.count == 0);
    module.pendingPolicy(nil, nil);
    assert(rejected == 1 && module.generations.count == 0);
    [module invalidate];
  }
}

static void testOmiFrames(void) {
  NSString *done = [NSString stringWithFormat:@"done: %@\n\n", [[@"{\"id\":\"message\",\"text\":\"Hello 世界\",\"sender\":\"ai\",\"created_at\":\"2026-09-07T00:00:00Z\"}" dataUsingEncoding:NSUTF8StringEncoding] base64EncodedStringWithOptions:0]];
  {
    __block NSMutableArray<NSString *> *frames = [NSMutableArray array];
    __block NSUInteger accepted = 0, rejected = 0;
    OmiGenerationDelegate *delegate = [[OmiGenerationDelegate alloc] initWithResolve:^(id value) { accepted++; } reject:^(NSString *code, NSString *message, NSError *error) { rejected++; } cleanup:^{}];
    delegate.omiChat = YES; delegate.responseStatus = 200; delegate.requestId = @"test";
    delegate.onFrame = ^(NSString *frame) { [frames addObject:frame]; };
    NSString *world = @"世界";
    NSData *worldBytes = [world dataUsingEncoding:NSUTF8StringEncoding];
    [delegate URLSession:nil dataTask:nil didReceiveData:[@"data: Hel" dataUsingEncoding:NSUTF8StringEncoding]];
    assert(accepted == 0 && frames.count == 0);
    [delegate URLSession:nil dataTask:nil didReceiveData:[@"lo " dataUsingEncoding:NSUTF8StringEncoding]];
    [delegate URLSession:nil dataTask:nil didReceiveData:[worldBytes subdataWithRange:NSMakeRange(0, 1)]];
    assert(accepted == 0 && frames.count == 0);
    [delegate URLSession:nil dataTask:nil didReceiveData:[worldBytes subdataWithRange:NSMakeRange(1, worldBytes.length - 1)]];
    [delegate URLSession:nil dataTask:nil didReceiveData:[@"\n\n" dataUsingEncoding:NSUTF8StringEncoding]];
    assert(accepted == 0 && frames.count == 1 && [frames[0] isEqual:@"data: Hello 世界\n\n"]);
    [delegate URLSession:nil dataTask:nil didReceiveData:[done dataUsingEncoding:NSUTF8StringEncoding]];
    assert(accepted == 1 && rejected == 0 && frames.count == 2);
  }
  for (NSString *frame in @[done, @"done: invalid!\n\n", [done stringByTrimmingCharactersInSet:NSCharacterSet.newlineCharacterSet], [@"x" stringByPaddingToLength:3 * 1024 * 1024 + 1 withString:@"x" startingAtIndex:0]]) {
    __block NSUInteger accepted = 0, rejected = 0, cleaned = 0;
    OmiGenerationDelegate *delegate = [[OmiGenerationDelegate alloc] initWithResolve:^(id value) { accepted++; } reject:^(NSString *code, NSString *message, NSError *error) { rejected++; } cleanup:^{ cleaned++; }];
    delegate.omiChat = YES; delegate.responseStatus = 200; delegate.requestId = @"test";
    [delegate URLSession:nil dataTask:nil didReceiveData:[frame dataUsingEncoding:NSUTF8StringEncoding]];
    [delegate URLSession:nil task:nil didCompleteWithError:nil];
    assert(accepted == ([frame isEqual:done] ? 1 : 0));
    assert(accepted + rejected == 1 && cleaned == 1 && delegate.reconnects == 0);
    [delegate cancel]; assert(cleaned == 1);
  }
  __block NSUInteger accepted = 0, rejected = 0;
  OmiGenerationDelegate *delegate = [[OmiGenerationDelegate alloc] initWithResolve:^(id value) { accepted++; } reject:^(NSString *code, NSString *message, NSError *error) { rejected++; } cleanup:^{}];
  delegate.omiChat = YES; delegate.responseStatus = 200; delegate.requestId = @"test";
  [delegate cancel];
  [delegate URLSession:nil dataTask:nil didReceiveData:[done dataUsingEncoding:NSUTF8StringEncoding]];
  assert(accepted == 0 && rejected == 1);
}

static void testCaptureQueryRoutes(void) {
  assert(OmiIsCaptureBackendPath(@"/v1/conversations"));
  assert(OmiIsCaptureBackendPath(@"/v1/conversations?limit=50&offset=0"));
  assert(OmiIsCaptureBackendPath(@"/v1/memories?limit=50"));
  assert(OmiIsCaptureBackendPath(@"/v1/tasks?limit=50&cursor=abc"));
  assert(OmiIsCaptureBackendPath(@"/v1/tasks/ops"));
  assert(OmiIsCaptureBackendPath(@"/v1/chat-messages?limit=50"));
  assert(OmiIsCaptureBackendPath(@"/v1/conversations#keep"));
  assert(!OmiIsCaptureBackendPath(@"/v1/apps?limit=50"));
  assert(!OmiIsCaptureBackendPath(@"/v1/conversations-extra?limit=50"));
  assert(OmiExamplePlatformRequestSupported(@"GET", @"/v1/conversations?limit=50"));
  assert(OmiExamplePlatformRequestSupported(@"GET", @"/v1/tasks?limit=2"));
  assert(!OmiExamplePlatformRequestSupported(@"POST", @"/v1/tasks"));
  OmiBackendPolicy *policy = [OmiBackendPolicy new];
  policy.url = [NSURL URLWithString:@"https://api.omi.me"];
  policy.captureURL = [NSURL URLWithString:@"https://synthetic.workers.dev"];
  policy.captureOriginRequired = YES;
  policy.token = @"synthetic-test";
  policy.clientId = @"test";
  policy.kind = OmiBackendCredentialKindCloud;
  assert([OmiRequestBaseURL(policy, @"/v1/conversations?limit=50").host isEqualToString:@"synthetic.workers.dev"]);
  assert([OmiRequestBaseURL(policy, @"/v1/tasks/ops").host isEqualToString:@"synthetic.workers.dev"]);
  assert([OmiRequestBaseURL(policy, @"/v1/apps").host isEqualToString:@"api.omi.me"]);
  policy.captureOriginRequired = NO;
  assert([OmiRequestBaseURL(policy, @"/v1/conversations?limit=50").host isEqualToString:@"api.omi.me"]);
}

int main() {
  @autoreleasepool {
    testSelectedContract();
    testCaptureQueryRoutes();
    testOmiFrames();
    testPendingOmiCancellation();
    NSString *identifier = NSUUID.UUID.UUIDString;
    NSString *root = [NSTemporaryDirectory() stringByAppendingPathComponent:identifier];
    NSString *tag = [@"omi-disposal-test-" stringByAppendingString:identifier];
    NSDictionary *owner = @{@"login":@"login", @"origin":@"https://example.invalid/", @"ownerKey":[@"capture-owner-v1:" stringByAppendingString:[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0]], @"receipt":[NSString stringWithFormat:@"capture1.%@.%@", [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0], [@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0]]};
    DisposalBackend *module = [DisposalBackend new];
    module.journalQueue = dispatch_queue_create("disposal-test", DISPATCH_QUEUE_SERIAL);
    module.recordingJournals = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return @"login"; }];
    NSDictionary *created = [module.recordingJournals create:owner input:@{@"deviceId":@"test", @"codec":@21} error:nil];
    assert(created != nil);
    assert([module.recordingJournals append:created[@"handle"] entry:@"[\"p\",\"AAAB\"]" error:nil] != nil);
    __block NSUInteger rejected = 0;
    [module createRecordingJournalWithInput:@{@"deviceId":@"late", @"codec":@21} resolver:^(id result) { abort(); } rejecter:^(NSString *code, NSString *message, NSError *error) { rejected++; }];
    dispatch_sync(module.journalQueue, ^{});
    assert(module.pendingOwner != nil);
    [module.session invalidateAndCancel];
    DisposalSession *network = [DisposalSession new];
    module.session = (NSURLSession *)network;
    __block NSUInteger contractRejected = 0;
    for (id expected in @[@"omi", @42]) {
      [module performNativeRequest:@{@"id":@"contract", @"path":@"/v3/action-items/task", @"method":@"PATCH", @"expectedApiContract":expected} receipt:nil expectedOrigin:nil expectedLogin:nil resolver:^(id value) { abort(); } rejecter:^(NSString *code, NSString *message, NSError *error) {
        assert([code isEqual:[expected isKindOfClass:NSString.class] ? @"OMI_HTTP_BACKEND_CHANGED" : @"OMI_HTTP_INVALID_REQUEST"]); contractRejected++;
      }];
    }
    assert(contractRejected == 2 && network.task == nil);
    __block NSUInteger httpRejected = 0;
    [module performNativeRequest:@{@"id":@"pending", @"path":@"/v1/conversations", @"method":@"GET"} receipt:nil expectedOrigin:nil expectedLogin:nil resolver:^(id value) { abort(); } rejecter:^(NSString *code, NSString *message, NSError *error) { assert([code isEqual:@"OMI_HTTP_CANCELLED"]); httpRejected++; }];
    assert(network.task.resumes == 1);
    [module invalidate];
    assert(network.invalidations == 1);
    network.completion([@"{}" dataUsingEncoding:NSUTF8StringEncoding], [[NSHTTPURLResponse alloc] initWithURL:[NSURL URLWithString:@"http://127.0.0.1:1/v1/conversations"] statusCode:200 HTTPVersion:@"HTTP/1.1" headerFields:@{}], nil);
    network.completion = nil;
    module.pendingOwner(owner);
    dispatch_sync(module.journalQueue, ^{});
    assert(rejected == 1);
    assert(httpRejected == 1);
    assert([module.recordingJournals list:owner error:nil] == nil);
    OmiRecordingJournals *replacement = [[OmiRecordingJournals alloc] initWithRoot:root keyTag:tag currentLogin:^NSString *{ return @"login"; }];
    NSArray *recovered = [replacement list:owner error:nil];
    assert(recovered.count == 1);
    assert([[replacement read:created[@"handle"] error:nil][@"entries"] count] == 1);
    [module performNativeRequest:@{@"id":@"late", @"path":@"/v1/conversations", @"method":@"GET"} receipt:nil expectedOrigin:nil expectedLogin:nil resolver:^(id value) { abort(); } rejecter:^(NSString *code, NSString *message, NSError *error) { assert([code isEqual:@"OMI_HTTP_CANCELLED"]); rejected++; }];
    assert(rejected == 2);
    module.hasListeners = YES;
    [module emitSessionInvalidated];
    [module invalidate];
    assert([replacement remove:created[@"handle"] error:nil]);
    [replacement dispose];
    module.pendingOwner = nil;
    assert([NSFileManager.defaultManager removeItemAtPath:root error:nil]);
    assert(SecItemDelete((__bridge CFDictionaryRef)@{(__bridge id)kSecClass:(__bridge id)kSecClassKey, (__bridge id)kSecAttrApplicationTag:[tag dataUsingEncoding:NSUTF8StringEncoding], (__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom}) == errSecSuccess);
    puts("Apple backend disposal releases encrypted journals and rejects delayed work");
  }
}
