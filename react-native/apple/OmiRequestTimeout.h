#import <Foundation/Foundation.h>

#include "omi_backend_policy.h"

// Timeout policy lives in native-core (omi_backend_request_timeout_seconds).
static NSTimeInterval OmiRequestTimeout(NSString *method, NSURL *url) {
  const char *methodUtf8 = method.UTF8String ?: "";
  const char *pathUtf8 = url.path.UTF8String ?: "";
  return (NSTimeInterval)omi_backend_request_timeout_seconds(methodUtf8, pathUtf8);
}
