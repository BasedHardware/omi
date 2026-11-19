// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#import <Foundation/Foundation.h>

@interface OrtExt : NSObject

typedef struct OrtStatus* (*ORTCAPIRegisterCustomOpsFnPtr)(struct OrtSessionOptions* /*options*/,
                                                           const struct OrtApiBase* /*api*/);

// Note: This returns the address of `RegisterCustomOps` function. At swift
// level, user can call this function to get the RegisterCustomOpsFnPtr
// and use the function pointer to register custom ops. See
// SwiftOnnxRuntimeExtensionsTests.swift for an example usage.
+ (nonnull ORTCAPIRegisterCustomOpsFnPtr)getRegisterCustomOpsFunctionPointer;

@end