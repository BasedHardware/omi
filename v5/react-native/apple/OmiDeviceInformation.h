#import <Foundation/Foundation.h>

static NSDictionary<NSString *, NSString *> *OmiInformationFields(void) {
  return @{ @"2A24": @"model", @"2A26": @"firmware", @"2A27": @"hardware", @"2A29": @"manufacturer", @"2A25": @"serial" };
}

static NSString *OmiDecodeDeviceInformation(NSData *data) {
  if (data.length == 0 || data.length > 512) return nil;
  NSString *value = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
  value = [value stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
  if (value.length == 0 || [value rangeOfCharacterFromSet:[NSCharacterSet controlCharacterSet]].location != NSNotFound) return nil;
  return value;
}
