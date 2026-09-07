#import <Foundation/Foundation.h>
#import <Security/Security.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static const NSUInteger OmiRecordingMaxEntryBytes = 1052672;
static const NSUInteger OmiRecordingMaxFileBytes = 33554432;
static const NSUInteger OmiRecordingMaxEntries = 131080;

static BOOL OmiRecordingError(NSError **error) {
  if (error != NULL) *error = [NSError errorWithDomain:@"OmiRecordingJournal" code:1 userInfo:nil];
  return NO;
}

@interface OmiRecordingLog : NSObject {
  int _descriptor;
  NSUInteger _nextSequence;
  BOOL _failed;
  NSData *_binding;
  id _privateKey;
}
- (instancetype)initWithPath:(NSString *)path key:(SecKeyRef)key binding:(NSData *)binding error:(NSError **)error;
- (NSArray<NSData *> *)readAll:(NSError **)error;
- (NSNumber *)append:(NSData *)payload error:(NSError **)error;
- (void)close;
@end

@implementation OmiRecordingLog
- (instancetype)initWithPath:(NSString *)path key:(SecKeyRef)key binding:(NSData *)binding error:(NSError **)error {
  self = [super init];
  if (self == nil) return nil;
  _descriptor = -1;
  if (binding.length != 32 || key == NULL) { OmiRecordingError(error); return nil; }
  _binding = [binding copy];
  _privateKey = (__bridge id)key;
  _descriptor = open(path.fileSystemRepresentation, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (_descriptor < 0 || flock(_descriptor, LOCK_EX | LOCK_NB) != 0) { OmiRecordingError(error); return nil; }
  if ([self readAll:error] == nil) return nil;
  if (_nextSequence == 0 && [self appendEntry:[NSData data] error:error] == nil) return nil;
  int directory = open(path.stringByDeletingLastPathComponent.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
  if (directory < 0) { OmiRecordingError(error); return nil; }
  int result = fsync(directory);
  close(directory);
  if (result != 0) { OmiRecordingError(error); return nil; }
  return self;
}

- (BOOL)readBytes:(void *)bytes length:(NSUInteger)length {
  NSUInteger offset = 0;
  while (offset < length) {
    ssize_t count = read(_descriptor, (unsigned char *)bytes + offset, length - offset);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return NO;
    offset += (NSUInteger)count;
  }
  return YES;
}

- (BOOL)writeBytes:(const void *)bytes length:(NSUInteger)length {
  NSUInteger offset = 0;
  while (offset < length) {
    ssize_t count = write(_descriptor, (const unsigned char *)bytes + offset, length - offset);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return NO;
    offset += (NSUInteger)count;
  }
  return YES;
}

- (NSArray<NSData *> *)readAll:(NSError **)error {
  @synchronized(self) {
    struct stat state;
    if (_descriptor < 0 || _failed || fstat(_descriptor, &state) != 0 || state.st_size > OmiRecordingMaxFileBytes || lseek(_descriptor, 0, SEEK_SET) < 0) {
      OmiRecordingError(error); return nil;
    }
    NSMutableArray<NSData *> *entries = [NSMutableArray array];
    NSUInteger sequence = 0;
    off_t offset = 0;
    while (offset < state.st_size) {
      uint32_t networkLength = 0;
      NSUInteger length = 0;
      BOOL torn = state.st_size - offset < 4;
      if (!torn) {
        if (![self readBytes:&networkLength length:4]) { _failed = YES; OmiRecordingError(error); return nil; }
        length = CFSwapInt32BigToHost(networkLength);
        if (length < 40 || length > OmiRecordingMaxEntryBytes + 256) { _failed = YES; OmiRecordingError(error); return nil; }
        torn = state.st_size - offset - 4 < (off_t)length;
      }
      if (torn) {
        if (ftruncate(_descriptor, offset) != 0 || fsync(_descriptor) != 0) { _failed = YES; OmiRecordingError(error); return nil; }
        break;
      }
      NSMutableData *encrypted = [NSMutableData dataWithLength:length];
      if (![self readBytes:encrypted.mutableBytes length:length]) { _failed = YES; OmiRecordingError(error); return nil; }
      NSData *plain = CFBridgingRelease(SecKeyCreateDecryptedData((__bridge SecKeyRef)_privateKey,
        kSecKeyAlgorithmECIESEncryptionStandardVariableIVX963SHA256AESGCM, (__bridge CFDataRef)encrypted, NULL));
      uint64_t storedSequence = 0;
      if (plain.length >= 40) memcpy(&storedSequence, (const unsigned char *)plain.bytes + 32, 8);
      if (plain.length < 40 || ![[plain subdataWithRange:NSMakeRange(0, 32)] isEqualToData:_binding]
          || CFSwapInt64BigToHost(storedSequence) != sequence || sequence >= OmiRecordingMaxEntries
          || (sequence == 0 && plain.length != 40)) { _failed = YES; OmiRecordingError(error); return nil; }
      if (sequence > 0) [entries addObject:[plain subdataWithRange:NSMakeRange(40, plain.length - 40)]];
      sequence++;
      offset += 4 + (off_t)length;
    }
    _nextSequence = sequence;
    return [entries copy];
  }
}

- (NSNumber *)append:(NSData *)payload error:(NSError **)error {
  @synchronized(self) {
    if (payload.length == 0 || payload.length > OmiRecordingMaxEntryBytes) { OmiRecordingError(error); return nil; }
    return [self appendEntry:payload error:error];
  }
}

- (NSNumber *)appendEntry:(NSData *)payload error:(NSError **)error {
  if (_descriptor < 0 || _failed || _nextSequence >= OmiRecordingMaxEntries) { OmiRecordingError(error); return nil; }
  NSMutableData *plain = [_binding mutableCopy];
  uint64_t sequence = CFSwapInt64HostToBig(_nextSequence);
  [plain appendBytes:&sequence length:8];
  [plain appendData:payload];
  SecKeyRef publicKey = SecKeyCopyPublicKey((__bridge SecKeyRef)_privateKey);
  NSData *encrypted = publicKey == NULL ? nil : CFBridgingRelease(SecKeyCreateEncryptedData(publicKey,
    kSecKeyAlgorithmECIESEncryptionStandardVariableIVX963SHA256AESGCM, (__bridge CFDataRef)plain, NULL));
  if (publicKey != NULL) CFRelease(publicKey);
  off_t end = lseek(_descriptor, 0, SEEK_END);
  if (encrypted == nil || end < 0 || (NSUInteger)end + 4 + encrypted.length > OmiRecordingMaxFileBytes) { OmiRecordingError(error); return nil; }
  uint32_t length = CFSwapInt32HostToBig((uint32_t)encrypted.length);
  if (![self writeBytes:&length length:4] || ![self writeBytes:encrypted.bytes length:encrypted.length] || fsync(_descriptor) != 0) {
    _failed = YES; OmiRecordingError(error); return nil;
  }
  return @(_nextSequence++);
}

- (void)close {
  @synchronized(self) {
    if (_descriptor >= 0) { flock(_descriptor, LOCK_UN); close(_descriptor); _descriptor = -1; }
  }
}
- (void)dealloc { [self close]; }
@end
