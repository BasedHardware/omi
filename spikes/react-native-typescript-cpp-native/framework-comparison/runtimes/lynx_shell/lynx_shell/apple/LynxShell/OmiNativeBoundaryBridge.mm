#import "OmiNativeBoundaryBridge.h"
#include "../../../../../../cpp/include/omi_native_boundary.h"
#include "../../../../../../cpp/src/omi_native_boundary.cpp"

@implementation OmiNativeBoundaryBridge

+ (NSString *)capabilities {
  char buffer[256] = {};
  if (omi_get_native_capabilities(buffer, sizeof(buffer)) != OMI_STATUS_OK) {
    return @"{\"error\":\"NATIVE_CAPABILITIES_UNAVAILABLE\"}";
  }
  return [NSString stringWithUTF8String:buffer] ?: @"{}";
}

+ (NSString *)normalizePacket:(NSString *)raw {
  NSData *input = [raw dataUsingEncoding:NSUTF8StringEncoding];
  if (input == nil) {
    return @"";
  }

  uint8_t output[4096] = {};
  size_t outputLength = 0;
  int32_t status = omi_normalize_packet(
      static_cast<const uint8_t *>(input.bytes), input.length,
      output, sizeof(output), &outputLength);
  if (status != OMI_STATUS_OK) {
    return [NSString stringWithFormat:@"ERROR:%d", status];
  }

  NSData *normalized = [NSData dataWithBytes:output length:outputLength];
  return [[NSString alloc] initWithData:normalized encoding:NSUTF8StringEncoding] ?: @"";
}

@end
