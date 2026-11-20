// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

import XCTest
import Foundation
@testable import OnnxRuntimeBindings
@testable import OnnxRuntimeExtensions

final class SwiftOnnxRuntimeExtensionsTests: XCTestCase {

    let modelPath: String = Bundle.module.url(forResource: "decode_image", withExtension: "onnx")!.path

    func testCreateSessionWithCustomOps() throws {
        let env = try ORTEnv(loggingLevel: ORTLoggingLevel.verbose)
        let options = try ORTSessionOptions()
        try options.setLogSeverityLevel(ORTLoggingLevel.verbose)
        try options.setIntraOpNumThreads(1)

        // Register Custom Ops library using function pointer
        let ortCustomOpsFnPtr = OrtExt.getRegisterCustomOpsFunctionPointer()
        try options.registerCustomOps(functionPointer: ortCustomOpsFnPtr)

        // Create the ORTSession
        _ = try ORTSession(env: env, modelPath: modelPath, sessionOptions: options)
    }
}