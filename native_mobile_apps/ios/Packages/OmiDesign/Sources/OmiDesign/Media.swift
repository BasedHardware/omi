import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// Omi's own imagery (copied from upstream `app/assets`), bundled with the design system.
public enum OmiMedia {
    public enum Background: String, CaseIterable {
        case bg1 = "onboarding-bg-1", bg2 = "onboarding-bg-2", bg3 = "onboarding-bg-3"
        case bg4 = "onboarding-bg-4", bg6 = "onboarding-bg-6"
    }

    #if canImport(UIKit)
        public static func image(_ name: String, ext: String = "png") -> UIImage? {
            guard let url = Bundle.module.url(forResource: name, withExtension: ext, subdirectory: "Media") else { return nil }
            return UIImage(contentsOfFile: url.path)
        }

        public static func background(_ background: Background) -> Image {
            image(background.rawValue, ext: "jpg").map(Image.init(uiImage:)) ?? Image(systemName: "photo")
        }

        public static var device: Image {
            image("omi-device").map(Image.init(uiImage:)) ?? Image(systemName: "circle.circle.fill")
        }

        /// Integration logo by backend key (google_calendar, gmail, todoist, …).
        public static func logo(_ key: String) -> Image? {
            image("logo-\(key)").map(Image.init(uiImage:))
        }
    #endif
}
