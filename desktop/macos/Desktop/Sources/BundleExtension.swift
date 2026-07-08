import Foundation

// Custom Bundle accessor for our resource bundle.
// This is necessary because:
// 1. Swift PM generates code that looks for the bundle at the app root
// 2. macOS code signing doesn't allow files at the app root (outside Contents/)
// 3. We need the bundle in Contents/Resources/ for proper code signing
// Note: We use "resourceBundle" instead of "module" to avoid conflicts with Swift PM's generated accessor
extension Foundation.Bundle {
    static let resourceBundle: Bundle = {
        let bundleName = "Omi Computer_Omi Computer"

        // For macOS app bundles, look in Contents/Resources/
        let resourcesPath = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources")
            .appendingPathComponent("\(bundleName).bundle")
            .path

        // Fallback: direct child of main bundle (for development builds)
        let mainPath = Bundle.main.bundleURL
            .appendingPathComponent("\(bundleName).bundle")
            .path

        if let bundle = Bundle(path: resourcesPath) {
            return bundle
        } else if let bundle = Bundle(path: mainPath) {
            return bundle
        }

        // If none found, crash with helpful message
        Swift.fatalError("could not load resource bundle: tried \(resourcesPath), \(mainPath)")
    }()
}
