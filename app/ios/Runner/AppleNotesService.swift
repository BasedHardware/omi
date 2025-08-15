import Foundation
import UIKit
import Flutter

class AppleNotesService {
    
    func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "shareToNotes":
            shareToNotes(call: call, result: result)
        case "isNotesAppAvailable":
            isNotesAppAvailable(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func shareToNotes(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let content = args["content"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS",
                               message: "Content is required",
                               details: nil))
            return
        }
        
        DispatchQueue.main.async {
            // Prefer connectedScenes over deprecated UIApplication.shared.windows (iOS 15+)
            let windowScene = UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
            let keyWindow = windowScene?.windows.first { $0.isKeyWindow }
            guard let rootViewController = keyWindow?.rootViewController ?? UIApplication.shared.windows.first?.rootViewController else {
                result(FlutterError(code: "NO_VIEW_CONTROLLER",
                                   message: "Could not find root view controller",
                                   details: nil))
                return
            }
            
            // Create share sheet with the content
            let activityViewController = UIActivityViewController(
                activityItems: [content],
                applicationActivities: nil
            )
            
            // Exclude certain activities to make Notes more prominent
            activityViewController.excludedActivityTypes = [
                .postToFacebook,
                .postToTwitter,
                .postToWeibo,
                .assignToContact,
                .saveToCameraRoll,
                .postToFlickr,
                .postToVimeo,
                .postToTencentWeibo
            ]
            
            // For iPad
            if let popover = activityViewController.popoverPresentationController {
                popover.sourceView = rootViewController.view
                popover.sourceRect = CGRect(x: rootViewController.view.bounds.midX,
                                           y: rootViewController.view.bounds.midY,
                                           width: 0, height: 0)
                popover.permittedArrowDirections = []
            }
            
            // Present the share sheet
            rootViewController.present(activityViewController, animated: true) {
                result(true)
            }
        }
    }
    
    private func isNotesAppAvailable(result: @escaping FlutterResult) {
        // Notes is always available on iOS, but we check if URL scheme works
        if let url = URL(string: "mobilenotes://") {
            let canOpen = UIApplication.shared.canOpenURL(url)
            result(canOpen)
        } else {
            result(false)
        }
    }
}