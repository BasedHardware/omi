#import "OmiRecordingLog.h"
#import <CommonCrypto/CommonDigest.h>

static NSString *OmiRecordingDigest(NSString *value) {
  NSData *bytes = [value dataUsingEncoding:NSUTF8StringEncoding];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(bytes.bytes, (CC_LONG)bytes.length, digest);
  NSMutableString *result = [NSMutableString string];
  for (NSUInteger index = 0; index < sizeof(digest); index++) [result appendFormat:@"%02x", digest[index]];
  return result;
}
static BOOL OmiRecordingMatches(NSString *value, NSString *pattern) {
  return [value isKindOfClass:NSString.class] && [value rangeOfString:pattern options:NSRegularExpressionSearch].location != NSNotFound;
}
static NSString *OmiRecordingUUIDPattern = @"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$";

@interface OmiRecordingJournals : NSObject {
  NSString *_root;
  NSString *_keyTag;
  NSString *(^_currentLogin)(void);
  NSMutableDictionary<NSString *, NSMutableDictionary *> *_entries;
}
- (instancetype)initWithRoot:(NSString *)root keyTag:(NSString *)keyTag currentLogin:(NSString *(^)(void))currentLogin;
- (NSDictionary *)create:(NSDictionary *)owner input:(NSDictionary *)input error:(NSError **)error;
- (NSArray *)list:(NSDictionary *)owner error:(NSError **)error;
- (NSDictionary *)read:(NSString *)handle error:(NSError **)error;
- (NSNumber *)append:(NSString *)handle entry:(NSString *)entry error:(NSError **)error;
- (NSDictionary *)ownerForRequest:(NSString *)handle request:(NSDictionary *)request error:(NSError **)error;
- (BOOL)acknowledgeOpen:(NSString *)handle request:(NSDictionary *)request response:(NSDictionary *)response error:(NSError **)error;
- (BOOL)remove:(NSString *)handle error:(NSError **)error;
- (void)close;
@end

@implementation OmiRecordingJournals
- (instancetype)initWithRoot:(NSString *)root keyTag:(NSString *)keyTag currentLogin:(NSString *(^)(void))currentLogin {
  self = [super init];
  if (self) { _root = [root copy]; _keyTag = [keyTag copy]; _currentLogin = [currentLogin copy]; _entries = [NSMutableDictionary dictionary]; }
  return self;
}
- (BOOL)valid:(NSDictionary *)owner error:(NSError **)error {
  if (![owner[@"login"] isEqual:_currentLogin()] || !OmiRecordingMatches(owner[@"ownerKey"], @"^capture-owner-v1:[0-9a-f]{64}$")
      || !OmiRecordingMatches(owner[@"receipt"], @"^capture1\\.[0-9a-f]{64}\\.[0-9a-f]{64}$")) return OmiRecordingError(error);
  return YES;
}
- (NSString *)partition:(NSDictionary *)owner {
  return OmiRecordingDigest([NSString stringWithFormat:@"omi-recording-partition-v1\n%@\n%@\n%@", owner[@"origin"], owner[@"ownerKey"], owner[@"login"]]);
}
- (BOOL)budget:(NSUInteger)extra creating:(BOOL)creating error:(NSError **)error {
  NSDirectoryEnumerator *enumerator = [NSFileManager.defaultManager enumeratorAtPath:_root];
  NSUInteger size = 0, count = 0;
  for (NSString *path in enumerator) {
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:[_root stringByAppendingPathComponent:path] error:error];
    if (attributes == nil) return NO;
    if ([attributes[NSFileType] isEqual:NSFileTypeRegular]) { size += [attributes[NSFileSize] unsignedIntegerValue]; count++; }
    if ([attributes[NSFileType] isEqual:NSFileTypeSymbolicLink]) return OmiRecordingError(error);
  }
  if (size + extra > 134217728 || (creating && count >= 64)) return OmiRecordingError(error);
  return YES;
}
- (SecKeyRef)copyKey:(NSError **)error CF_RETURNS_RETAINED {
  NSData *tag = [_keyTag dataUsingEncoding:NSUTF8StringEncoding];
  NSDictionary *query = @{(__bridge id)kSecClass:(__bridge id)kSecClassKey, (__bridge id)kSecAttrApplicationTag:tag,
    (__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom, (__bridge id)kSecReturnRef:@YES};
  CFTypeRef found = NULL;
  OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &found);
  if (status == errSecSuccess) return (SecKeyRef)found;
  if (status != errSecItemNotFound) { OmiRecordingError(error); return NULL; }
  SecKeyRef key = SecKeyCreateRandomKey((__bridge CFDictionaryRef)@{
    (__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom,
    (__bridge id)kSecAttrKeySizeInBits:@256,
    (__bridge id)kSecPrivateKeyAttrs:@{(__bridge id)kSecAttrIsPermanent:@YES, (__bridge id)kSecAttrApplicationTag:tag,
      (__bridge id)kSecAttrAccessible:(__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly}}, NULL);
  if (key == NULL) OmiRecordingError(error);
  return key;
}
- (OmiRecordingLog *)open:(NSDictionary *)owner identifier:(NSString *)identifier error:(NSError **)error {
  NSString *partition = [self partition:owner];
  NSString *directory = [_root stringByAppendingPathComponent:partition];
  if (![NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:error]) return nil;
  [[NSURL fileURLWithPath:_root] setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
  for (NSString *parent in @[_root.stringByDeletingLastPathComponent, _root]) {
    int descriptor = open(parent.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) { OmiRecordingError(error); return nil; }
    int result = fsync(descriptor); close(descriptor);
    if (result != 0) { OmiRecordingError(error); return nil; }
  }
  NSString *binding = OmiRecordingDigest([NSString stringWithFormat:@"%@\n%@", partition, identifier]);
  NSMutableData *bytes = [NSMutableData dataWithLength:32];
  for (NSUInteger index = 0; index < 32; index++) {
    unsigned int value = 0; [[NSScanner scannerWithString:[binding substringWithRange:NSMakeRange(index * 2, 2)]] scanHexInt:&value];
    ((unsigned char *)bytes.mutableBytes)[index] = (unsigned char)value;
  }
  SecKeyRef key = [self copyKey:error];
  if (key == NULL) return nil;
  OmiRecordingLog *log = [[OmiRecordingLog alloc] initWithPath:[directory stringByAppendingPathComponent:[identifier stringByAppendingString:@".journal"]] key:key binding:bytes error:error];
  CFRelease(key);
  return log;
}
- (NSDictionary *)state:(NSMutableDictionary *)entry includeEntries:(BOOL)includeEntries error:(NSError **)error {
  NSArray<NSData *> *records = includeEntries ? [entry[@"log"] readAll:error] : @[];
  if (records == nil) return nil;
  NSMutableArray *values = [NSMutableArray array];
  for (NSData *record in records) if (record.length > 0 && ((const unsigned char *)record.bytes)[0] == 0) {
    NSString *value = [[NSString alloc] initWithData:[record subdataWithRange:NSMakeRange(1, record.length - 1)] encoding:NSUTF8StringEncoding];
    if (value == nil) { OmiRecordingError(error); return nil; }
    [values addObject:value];
  }
  return @{ @"handle":entry[@"id"], @"captureId":entry[@"id"], @"deviceId":entry[@"input"][@"deviceId"],
    @"deviceName":entry[@"input"][@"deviceName"], @"codec":entry[@"input"][@"codec"],
    @"sessionId":entry[@"sessionId"] ?: NSNull.null, @"entries":values };
}
- (NSData *)record:(unsigned char)kind payload:(NSData *)payload {
  NSMutableData *record = [NSMutableData dataWithBytes:&kind length:1]; [record appendData:payload]; return record;
}
- (NSDictionary *)create:(NSDictionary *)owner input:(NSDictionary *)input error:(NSError **)error {
  if (![self valid:owner error:error] || ![self budget:4096 creating:YES error:error]) return nil;
  NSString *device = input[@"deviceId"];
  id name = input[@"deviceName"] ?: NSNull.null;
  NSNumber *codec = input[@"codec"];
  if (![device isKindOfClass:NSString.class] || device.length == 0 || device.length > 256
      || (name != NSNull.null && (![name isKindOfClass:NSString.class] || [name length] > 256))
      || ![codec isKindOfClass:NSNumber.class] || codec.doubleValue < 0 || codec.doubleValue > 255 || codec.doubleValue != codec.integerValue) { OmiRecordingError(error); return nil; }
  NSString *identifier = NSUUID.UUID.UUIDString.lowercaseString;
  NSDictionary *metadata = @{ @"deviceId":device, @"deviceName":name, @"codec":codec };
  OmiRecordingLog *log = [self open:owner identifier:identifier error:error];
  if (log == nil) return nil;
  if ([log append:[self record:1 payload:[NSJSONSerialization dataWithJSONObject:metadata options:0 error:error]] error:error] == nil) { [log close]; return nil; }
  NSMutableDictionary *entry = [@{ @"id":identifier, @"owner":[owner copy], @"input":metadata, @"log":log } mutableCopy];
  _entries[identifier] = entry;
  return [self state:entry includeEntries:YES error:error];
}
- (NSArray *)list:(NSDictionary *)owner error:(NSError **)error {
  if (![self valid:owner error:error]) return nil;
  [self close];
  NSString *directory = [_root stringByAppendingPathComponent:[self partition:owner]];
  if (![NSFileManager.defaultManager fileExistsAtPath:directory]) return @[];
  NSArray *files = [NSFileManager.defaultManager contentsOfDirectoryAtPath:directory error:error];
  if (files == nil) return nil;
  if (files.count > 64) { OmiRecordingError(error); return nil; }
  NSMutableArray *result = [NSMutableArray array];
  for (NSString *file in [files sortedArrayUsingSelector:@selector(compare:)]) {
    @autoreleasepool {
    if (![file.pathExtension isEqual:@"journal"]) continue;
    NSString *identifier = file.stringByDeletingPathExtension;
    if (!OmiRecordingMatches(identifier, OmiRecordingUUIDPattern)) { OmiRecordingError(error); return nil; }
    OmiRecordingLog *log = [self open:owner identifier:identifier error:error];
    if (log == nil) return nil;
    NSArray<NSData *> *records = [log readAll:error];
    if (records == nil) { [log close]; return nil; }
    if (records.count == 0) {
      [log close];
      if (![NSFileManager.defaultManager removeItemAtPath:[directory stringByAppendingPathComponent:file] error:error]) return nil;
      int descriptor = open(directory.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
      if (descriptor < 0) { OmiRecordingError(error); return nil; }
      int synced = fsync(descriptor); close(descriptor);
      if (synced != 0) { OmiRecordingError(error); return nil; }
      continue;
    }
    NSData *first = records[0];
    if (first.length < 2 || ((const unsigned char *)first.bytes)[0] != 1) { [log close]; OmiRecordingError(error); return nil; }
    id input = [NSJSONSerialization JSONObjectWithData:[first subdataWithRange:NSMakeRange(1, first.length - 1)] options:0 error:error];
    if (![input isKindOfClass:NSDictionary.class]) { [log close]; OmiRecordingError(error); return nil; }
    NSMutableDictionary *entry = [@{ @"id":identifier, @"owner":[owner copy], @"input":input, @"log":log } mutableCopy];
    for (NSUInteger index = 1; index < records.count; index++) {
      NSData *record = records[index];
      if (record.length == 0) { [log close]; OmiRecordingError(error); return nil; }
      unsigned char kind = ((const unsigned char *)record.bytes)[0];
      if (kind == 2) {
        NSString *session = [[NSString alloc] initWithData:[record subdataWithRange:NSMakeRange(1, record.length - 1)] encoding:NSUTF8StringEncoding];
        if (!OmiRecordingMatches(session, OmiRecordingUUIDPattern) || (entry[@"sessionId"] != nil && ![entry[@"sessionId"] isEqual:session])) { [log close]; OmiRecordingError(error); return nil; }
        entry[@"sessionId"] = session;
      } else if (kind != 0) { [log close]; OmiRecordingError(error); return nil; }
    }
    _entries[identifier] = entry;
    NSDictionary *value = [self state:entry includeEntries:NO error:error];
    if (value == nil) return nil;
    [result addObject:value];
    }
  }
  return result;
}
- (NSMutableDictionary *)entry:(NSString *)handle error:(NSError **)error {
  NSMutableDictionary *entry = _entries[handle];
  if (entry == nil || ![self valid:entry[@"owner"] error:error]) { OmiRecordingError(error); return nil; }
  return entry;
}
- (NSDictionary *)read:(NSString *)handle error:(NSError **)error {
  NSMutableDictionary *entry = [self entry:handle error:error];
  return entry == nil ? nil : [self state:entry includeEntries:YES error:error];
}
- (NSNumber *)append:(NSString *)handle entry:(NSString *)value error:(NSError **)error {
  if (![value isKindOfClass:NSString.class] || value.length > OmiRecordingMaxEntryBytes - 1) { OmiRecordingError(error); return nil; }
  NSMutableDictionary *entry = [self entry:handle error:error];
  NSData *bytes = [value isKindOfClass:NSString.class] ? [value dataUsingEncoding:NSUTF8StringEncoding] : nil;
  if (entry == nil || bytes == nil || ![self budget:bytes.length + 261 creating:NO error:error]) return nil;
  return [entry[@"log"] append:[self record:0 payload:bytes] error:error];
}
- (NSDictionary *)ownerForRequest:(NSString *)handle request:(NSDictionary *)request error:(NSError **)error {
  NSMutableDictionary *entry = [self entry:handle error:error];
  if (entry == nil) return nil;
  NSString *path = request[@"path"], *method = request[@"method"];
  if ([path isEqual:@"/v1/device-sessions"] && [method isEqual:@"POST"]) {
    if (![request[@"body"] isKindOfClass:NSString.class]) { OmiRecordingError(error); return nil; }
    id body = [NSJSONSerialization JSONObjectWithData:[request[@"body"] dataUsingEncoding:NSUTF8StringEncoding] options:0 error:error];
    if (![body isKindOfClass:NSDictionary.class] || ![body[@"captureId"] isEqual:entry[@"id"]]
        || ![body[@"deviceId"] isEqual:entry[@"input"][@"deviceId"]] || ![body[@"codec"] isEqual:entry[@"input"][@"codec"]]
        || ![(body[@"deviceName"] ?: NSNull.null) isEqual:entry[@"input"][@"deviceName"]]) { OmiRecordingError(error); return nil; }
  } else {
    NSString *session = entry[@"sessionId"];
    NSString *base = [@"/v1/device-sessions/" stringByAppendingString:session ?: @""];
    if (session == nil || !(([method isEqual:@"POST"] && [@[[base stringByAppendingString:@"/audio"], [base stringByAppendingString:@"/complete"], [base stringByAppendingString:@"/transcribe"]] containsObject:path])
      || ([method isEqual:@"GET"] && [@[base, [base stringByAppendingString:@"/transcript"]] containsObject:path]))) { OmiRecordingError(error); return nil; }
  }
  return entry[@"owner"];
}
- (BOOL)acknowledgeOpen:(NSString *)handle request:(NSDictionary *)request response:(NSDictionary *)response error:(NSError **)error {
  NSMutableDictionary *entry = [self entry:handle error:error];
  if (entry == nil) return NO;
  if (![request[@"path"] isEqual:@"/v1/device-sessions"] || [response[@"status"] integerValue] < 200 || [response[@"status"] integerValue] >= 300) return YES;
  if (![response[@"body"] isKindOfClass:NSString.class]) return OmiRecordingError(error);
  id body = [NSJSONSerialization JSONObjectWithData:[response[@"body"] dataUsingEncoding:NSUTF8StringEncoding] options:0 error:error];
  NSDictionary *session = [body isKindOfClass:NSDictionary.class] ? body[@"session"] : nil;
  NSString *identifier = [session isKindOfClass:NSDictionary.class] ? session[@"id"] : nil;
  if (!OmiRecordingMatches(identifier, OmiRecordingUUIDPattern) || ![session[@"deviceId"] isEqual:entry[@"input"][@"deviceId"]]
    || ![session[@"codec"] isEqual:entry[@"input"][@"codec"]] || (entry[@"sessionId"] != nil && ![entry[@"sessionId"] isEqual:identifier])) return OmiRecordingError(error);
  if (entry[@"sessionId"] == nil) {
    if (![self budget:512 creating:NO error:error] || [entry[@"log"] append:[self record:2 payload:[identifier dataUsingEncoding:NSUTF8StringEncoding]] error:error] == nil) return NO;
    entry[@"sessionId"] = identifier;
  }
  return YES;
}
- (BOOL)remove:(NSString *)handle error:(NSError **)error {
  NSMutableDictionary *entry = [self entry:handle error:error];
  if (entry == nil) return NO;
  [entry[@"log"] close];
  NSString *directory = [_root stringByAppendingPathComponent:[self partition:entry[@"owner"]]];
  if (![NSFileManager.defaultManager removeItemAtPath:[directory stringByAppendingPathComponent:[handle stringByAppendingString:@".journal"]] error:error]) return NO;
  int descriptor = open(directory.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
  if (descriptor < 0) return OmiRecordingError(error);
  int result = fsync(descriptor); close(descriptor);
  if (result != 0) return OmiRecordingError(error);
  [_entries removeObjectForKey:handle];
  return YES;
}
- (void)close { for (NSDictionary *entry in _entries.allValues) [entry[@"log"] close]; [_entries removeAllObjects]; }
@end
