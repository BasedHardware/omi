#import "../../macos/RnRuntime-macOS/OmiBackendModule.mm"
#include <cassert>

@implementation RCTEventEmitter
- (void)invalidate {}
- (void)sendEventWithName:(NSString *)name body:(id)body { abort(); }
@end
BOOL OmiAuthEnvironmentCloudTokensIgnored(void) { return YES; }
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

int main() {
  @autoreleasepool {
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
