#import "OmiDeviceInformation.h"
#include <cassert>

int main() {
  @autoreleasepool {
    assert([OmiInformationFields()[@"2A24"] isEqualToString:@"model"]);
    assert([OmiInformationFields()[@"2A26"] isEqualToString:@"firmware"]);
    assert([OmiInformationFields()[@"2A27"] isEqualToString:@"hardware"]);
    assert([OmiInformationFields()[@"2A29"] isEqualToString:@"manufacturer"]);
    assert([OmiInformationFields()[@"2A25"] isEqualToString:@"serial"]);
    assert([OmiDecodeDeviceInformation([@" Omi 1.2 " dataUsingEncoding:NSUTF8StringEncoding]) isEqualToString:@"Omi 1.2"]);
    for (NSString *value in @[@"", @"  ", @"a\nb"]) assert(OmiDecodeDeviceInformation([value dataUsingEncoding:NSUTF8StringEncoding]) == nil);
    const unsigned char invalid[] = {0xc3, 0x28};
    assert(OmiDecodeDeviceInformation([NSData dataWithBytes:invalid length:2]) == nil);
    assert(OmiDecodeDeviceInformation([NSMutableData dataWithLength:513]) == nil);
  }
}
