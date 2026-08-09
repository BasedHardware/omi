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

+ (NSString *)normalizePacket:(NSString *)rawBase64 {
  NSData *input = [[NSData alloc] initWithBase64EncodedString:rawBase64 options:0];
  if (input == nil) {
    return @"{\"status\":-1,\"payloadLength\":0,\"payloadBase64\":\"\"}";
  }

  NSMutableData *output = [NSMutableData dataWithLength:input.length];
  size_t outputLength = 0;
  const int32_t status = omi_normalize_packet(
      static_cast<const uint8_t *>(input.bytes), input.length,
      static_cast<uint8_t *>(output.mutableBytes), output.length, &outputLength);
  output.length = outputLength;
  NSString *payload = [output base64EncodedStringWithOptions:0];
  return [NSString stringWithFormat:
                   @"{\"status\":%d,\"payloadLength\":%lu,\"payloadBase64\":\"%@\"}",
                   status, static_cast<unsigned long>(outputLength), payload];
}

@end
