#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>

static NSString *OmiRewindOwner(NSDictionary *identity) {
  NSData *bytes = [[NSString stringWithFormat:@"%@:%@", identity[@"uid"], identity[@"login"]] dataUsingEncoding:NSUTF8StringEncoding];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(bytes.bytes, (CC_LONG)bytes.length, digest);
  NSMutableString *value = [NSMutableString string];
  for (NSUInteger index = 0; index < sizeof(digest); index++) [value appendFormat:@"%02x", digest[index]];
  return value;
}
