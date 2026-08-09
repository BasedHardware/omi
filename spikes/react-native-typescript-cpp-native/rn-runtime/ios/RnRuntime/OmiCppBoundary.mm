#import "OmiCppBoundary.h"

#include <cstring>
#include <vector>

#include "omi_native_boundary.h"

@implementation OmiCppBoundary

RCT_EXPORT_MODULE(OmiCppBoundary)

RCT_EXPORT_METHOD(normalizePacket:(NSArray<NSNumber *> *)rawData
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject) {
  std::vector<uint8_t> raw;
  raw.reserve(rawData.count);
  for (NSNumber *value in rawData) {
    NSInteger byte = value.integerValue;
    if (byte < 0 || byte > UINT8_MAX) {
      reject(@"invalid_param", @"Packet bytes must be in the range 0...255", nil);
      return;
    }
    raw.push_back((uint8_t)byte);
  }

  std::vector<uint8_t> payload(raw.size());
  size_t payloadLength = 0;
  int32_t status = omi_normalize_packet(
      raw.data(), raw.size(), payload.data(), payload.size(), &payloadLength);
  if (status != OMI_STATUS_OK) {
    reject([NSString stringWithFormat:@"omi_status_%d", status],
           @"The C++ boundary rejected the packet", nil);
    return;
  }

  NSMutableArray<NSNumber *> *result = [NSMutableArray arrayWithCapacity:payloadLength];
  for (size_t index = 0; index < payloadLength; ++index) {
    [result addObject:@(payload[index])];
  }
  resolve(result);
}

RCT_EXPORT_METHOD(getNativeCapabilities:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject) {
  char buffer[256] = {0};
  int32_t status = omi_get_native_capabilities(buffer, sizeof(buffer));
  if (status != OMI_STATUS_OK) {
    reject([NSString stringWithFormat:@"omi_status_%d", status],
           @"The C++ boundary could not return capabilities", nil);
    return;
  }

  NSData *data = [NSData dataWithBytes:buffer length:strlen(buffer)];
  NSError *error = nil;
  id capabilities = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
  if (error != nil || capabilities == nil) {
    reject(@"invalid_capabilities", @"The C++ capability JSON was invalid", error);
    return;
  }
  resolve(capabilities);
}

@end
