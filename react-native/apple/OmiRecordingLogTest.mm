#import "OmiRecordingLog.h"
#include <cassert>
#include <sys/wait.h>
#include <signal.h>

int main() {
  @autoreleasepool {
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:nil]);
    NSString *path = [directory stringByAppendingPathComponent:@"capture"];
    SecKeyRef key = SecKeyCreateRandomKey((__bridge CFDictionaryRef)@{(__bridge id)kSecAttrKeyType:(__bridge id)kSecAttrKeyTypeECSECPrimeRandom, (__bridge id)kSecAttrKeySizeInBits:@256}, NULL);
    assert(key != NULL);
    NSMutableData *binding = [NSMutableData dataWithLength:32];
    NSData *payload = [@"Synthetic packet, never real user data" dataUsingEncoding:NSUTF8StringEncoding];
    NSError *error = nil;
    OmiRecordingLog *log = [[OmiRecordingLog alloc] initWithPath:path key:key binding:binding error:&error];
    assert(log != nil && error == nil);
    assert([[log append:payload error:&error] isEqual:@1]);
    assert([[log append:[NSData dataWithBytes:"abc" length:3] error:&error] isEqual:@2]);
    assert([[OmiRecordingLog alloc] initWithPath:path key:key binding:binding error:&error] == nil);
    assert([log append:[NSMutableData dataWithLength:OmiRecordingMaxEntryBytes + 1] error:&error] == nil);
    [log close];
    NSData *original = [NSData dataWithContentsOfFile:path];
    assert([original rangeOfData:payload options:0 range:NSMakeRange(0, original.length)].location == NSNotFound);
    const char *crashPath = path.fileSystemRepresentation;
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
      int torn = open(crashPath, O_WRONLY | O_APPEND);
      unsigned char tail[] = {0, 0, 0, 100, 1, 2, 3};
      if (write(torn, tail, sizeof(tail)) != sizeof(tail)) _exit(1);
      kill(getpid(), SIGKILL);
      _exit(2);
    }
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
    log = [[OmiRecordingLog alloc] initWithPath:path key:key binding:binding error:&error];
    assert(log != nil);
    assert([log readAll:&error].count == 2);
    assert([[log readAll:&error][0] isEqualToData:payload]);
    assert([NSData dataWithContentsOfFile:path].length == original.length);
    assert([[log append:[NSData dataWithBytes:"d" length:1] error:&error] isEqual:@3]);
    [log close];
    NSMutableData *other = [binding mutableCopy]; ((unsigned char *)other.mutableBytes)[0] = 1;
    assert([[OmiRecordingLog alloc] initWithPath:path key:key binding:other error:&error] == nil);
    NSMutableData *tampered = [[NSData dataWithContentsOfFile:path] mutableCopy];
    ((unsigned char *)tampered.mutableBytes)[40] ^= 1;
    assert([tampered writeToFile:path atomically:NO]);
    assert([[OmiRecordingLog alloc] initWithPath:path key:key binding:binding error:&error] == nil);
    assert([[NSData dataWithContentsOfFile:path] isEqualToData:tampered]);
    CFRelease(key);
    assert([[NSFileManager defaultManager] removeItemAtPath:directory error:nil]);
    puts("Apple encrypted recording log restart, torn tail, ownership, tamper and budget checks passed");
  }
}
