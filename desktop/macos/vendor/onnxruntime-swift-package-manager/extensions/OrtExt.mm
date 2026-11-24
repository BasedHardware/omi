// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#import "OrtExt.h"

#include "onnxruntime_extensions/onnxruntime_extensions.h"

@implementation OrtExt

+ (nonnull ORTCAPIRegisterCustomOpsFnPtr)getRegisterCustomOpsFunctionPointer {
  return RegisterCustomOps;
}

@end