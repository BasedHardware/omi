import SwiftUI
import UIKit

/// Owns temporary presentation only. Input is returned to the existing service owner on explicit Save.
@available(iOS 16.0, *)
@MainActor
final class NativeModalPresenter: NSObject, UIAdaptivePresentationControllerDelegate {
    private let rootController: () -> UIViewController?
    private var active: Presentation?

    @MainActor
    private final class Presentation {
        let id: Int
        let controller: UIViewController
        let initial: NativeSurfaceSnapshot
        let state: NativeSurfaceState?
        let cancelID: String
        let guardEdits: Bool
        let discard: [String: String]
        let completion: (Any?) -> Void
        var asking = false

        init(id: Int, controller: UIViewController, initial: NativeSurfaceSnapshot,
             state: NativeSurfaceState?, cancelID: String, guardEdits: Bool,
             discard: [String: String], completion: @escaping (Any?) -> Void) {
            self.id = id
            self.controller = controller
            self.initial = initial
            self.state = state
            self.cancelID = cancelID
            self.guardEdits = guardEdits
            self.discard = discard
            self.completion = completion
        }

        var dirty: Bool { guardEdits && state?.snapshot.sections != initial.sections }
    }

    init(rootController: @escaping () -> UIViewController?) {
        self.rootController = rootController
    }

    func present(_ input: Any?, completion: @escaping (Any?) -> Void) throws {
        guard active == nil, let args = input as? [String: Any],
              let id = args["requestId"] as? Int, id >= 0,
              let cancelID = args["cancelId"] as? String,
              let snapshotInput = args["snapshot"],
              let discard = args["discard"] as? [String: String],
              let root = rootController() else { throw PresentationError.unavailable }
        let snapshot = try NativeSurfaceSnapshot.decode(snapshotInput)
        guard snapshot.chat == nil, !snapshot.toolbar.isEmpty,
              snapshot.toolbar.allSatisfy({ $0.kind == "button" }),
              snapshot.toolbar.contains(where: { $0.id == cancelID && $0.enabled }) else { throw PresentationError.invalid }
        var parent = root
        while let presented = parent.presentedViewController { parent = presented }
        guard parent.viewIfLoaded?.window != nil, !parent.isBeingDismissed else {
            throw PresentationError.unavailable
        }
        let controller: UIViewController
        var state: NativeSurfaceState?
        if args["alert"] as? Bool == true {
            guard snapshot.sections.flatMap(\.rows).allSatisfy({ $0.kind == "label" }) else {
                throw PresentationError.invalid
            }
            let alert = UIAlertController(title: snapshot.title,
                                          message: snapshot.sections.flatMap(\.rows).map(\.title).joined(separator: "\n"),
                                          preferredStyle: .alert)
            for row in snapshot.toolbar {
                let style: UIAlertAction.Style = row.id == cancelID ? .cancel : row.destructive ? .destructive : .default
                let action = UIAlertAction(title: row.title, style: style) { [weak self] _ in
                    self?.finish(id: id, action: row.id)
                }
                action.isEnabled = row.enabled
                alert.addAction(action)
            }
            controller = alert
        } else {
            let form = NativeSurfaceState(snapshot: snapshot) { [weak self] rowID, value in
                guard let self, let active = self.active, active.id == id else { throw PresentationError.unavailable }
                if let state = active.state,
                   let row = state.snapshot.sections.flatMap(\.rows).first(where: { $0.id == rowID }) {
                    let typed: NativeSurfaceRow.Value
                    if let text = value as? String { typed = .text(text) }
                    else if let flag = value as? Bool { typed = .bool(flag) }
                    else { throw PresentationError.invalid }
                    let replacement = row.replacingValue(typed)
                    guard replacement.hasValidValue else { throw PresentationError.invalid }
                    state.update(state.snapshot.replacingValue(id: rowID, value: typed))
                } else if rowID == cancelID {
                    self.requestDismissal(active)
                } else if snapshot.toolbar.contains(where: { $0.id == rowID && $0.enabled }) {
                    self.finish(id: id, action: rowID)
                } else { throw PresentationError.invalid }
            }
            state = form
            controller = UIHostingController(rootView: NativeSurfaceView(state: form))
            controller.modalPresentationStyle = .pageSheet
            controller.isModalInPresentation = args["dismissible"] as? Bool == false
            controller.sheetPresentationController?.prefersGrabberVisible = args["dismissible"] as? Bool != false
        }
        controller.overrideUserInterfaceStyle = snapshot.appearance == "system" ? .unspecified
            : snapshot.appearance == "dark" ? .dark : .light
        active = Presentation(id: id, controller: controller, initial: snapshot, state: state,
                              cancelID: cancelID, guardEdits: args["guardEdits"] as? Bool == true,
                              discard: discard, completion: completion)
        parent.present(controller, animated: true)
        // UIAlertController owns its presentation delegate. Editable sheets use ours to guard drafts.
        if state != nil { controller.presentationController?.delegate = self }
    }

    func dismiss(id: Int) { finish(id: id, action: nil) }

    private func finish(id: Int, action: String?) {
        guard let presentation = active, presentation.id == id else { return }
        let snapshot = presentation.state?.snapshot ?? presentation.initial
        let values = Dictionary(snapshot.sections.flatMap(\.rows).compactMap { row -> (String, Any)? in
            switch row.value {
            case let .text(text): return (row.id, text)
            case let .bool(flag): return (row.id, flag)
            case nil: return nil
            }
        }, uniquingKeysWith: { _, latest in latest })
        presentation.state?.invalidate()
        active = nil
        presentation.controller.dismiss(animated: true) {
            presentation.completion(action.map { ["action": $0, "values": values] })
        }
    }

    private func requestDismissal(_ presentation: Presentation) {
        guard presentation.dirty else { finish(id: presentation.id, action: nil); return }
        guard !presentation.asking else { return }
        presentation.asking = true
        let alert = UIAlertController(title: presentation.discard["title"],
                                      message: presentation.discard["message"], preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: presentation.discard["cancel"], style: .cancel) { _ in
            presentation.asking = false
        })
        alert.addAction(UIAlertAction(title: presentation.discard["confirm"], style: .destructive) { [weak self] _ in
            presentation.asking = false
            self?.finish(id: presentation.id, action: nil)
        })
        presentation.controller.present(alert, animated: true)
    }

    func presentationControllerShouldDismiss(_ presentationController: UIPresentationController) -> Bool {
        !(active?.dirty ?? false)
    }

    func presentationControllerDidAttemptToDismiss(_ presentationController: UIPresentationController) {
        if let active { requestDismissal(active) }
    }

    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        guard let presentation = active else { return }
        presentation.state?.invalidate()
        active = nil
        presentation.completion(nil)
    }

    enum PresentationError: Error { case invalid, unavailable }
}
