//
//  ScreenCaptureManager.swift
//  Runner
//
//  Created by Omi on 2025-09-26.
//

import AppKit
import Foundation
import ImageIO

class ScreenCaptureManager {
    static func captureScreen() -> URL? {
        let fileManager = FileManager.default
        guard let documentsDirectory = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            print("Error: Could not find documents directory.")
            return nil
        }
        let omiDirectory = documentsDirectory.appendingPathComponent("Omi")
        let screenshotsDirectory = omiDirectory.appendingPathComponent("Screenshots")

        do {
            try fileManager.createDirectory(at: screenshotsDirectory, withIntermediateDirectories: true, attributes: nil)
        } catch {
            print("Error creating directory: \(error)")
            return nil
        }

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let timestamp = formatter.string(from: Date())
        let fileName = "screenshot-\(timestamp).png"
        let fileURL = screenshotsDirectory.appendingPathComponent(fileName)

        guard let image = CGDisplayCreateImage(CGMainDisplayID()) else {
            print("Error: Could not capture screen.")
            return nil
        }

        guard let destination = CGImageDestinationCreateWithURL(fileURL as CFURL, "public.png" as CFString, 1, nil) else {
            print("Error: Could not create image destination.")
            return nil
        }
        
        CGImageDestinationAddImage(destination, image, nil)
        
        if !CGImageDestinationFinalize(destination) {
            print("Error: Could not save image.")
            return nil
        }

        print("Screenshot saved to \(fileURL.path)")
        return fileURL
    }
}
