import SwiftUI
import UIKit

/// Owns temporary presentation only. Input is returned to the existing service owner on explicit Save.
///
/// One presentation is active at a time. Its completion is always `{action?, values, reason}`:
/// 'action' for an enabled toolbar action (the only reason that carries values), 'cancel' for the
/// cancel row, 'dismissed' for a swipe or when UIKit fails to show it or another owner removes it,
/// and 'programmatic' for `dismiss(id:)`, which Dart sends for its own reasons (a dismissal signal,
/// a session change, an unmounted caller) and reports with those.
@available(iOS 16.0, *)
@MainActor
final class NativeModalPresenter: NSObject, UIAdaptivePresentationControllerDelegate {
    private let rootController: () -> UIViewController?
    private var active: Presentation?

    @MainActor
    private final class Presentation {
        let id: Int
        let controller: UIViewController
        let initial: NativeSurfaceSnapshot?
        let state: NativeSurfaceState?
        let cancelID: String
        let guardEdits: Bool
        /// A swipe may close it. A non-dismissible sheet ignores swipes; its own actions still close it.
        let dismissible: Bool
        let discard: [String: String]
        let completion: (Any?) -> Void
        var asking = false
        /// UIKit finished presenting it. A dismissal requested earlier waits here, because UIKit
        /// ignores a dismissal while the presentation is still animating in.
        var shown = false
        var whenShown: (() -> Void)?
        var monitor: Task<Void, Never>?

        init(id: Int, controller: UIViewController, initial: NativeSurfaceSnapshot?,
             state: NativeSurfaceState?, cancelID: String, guardEdits: Bool, dismissible: Bool,
             discard: [String: String], completion: @escaping (Any?) -> Void) {
            self.id = id
            self.controller = controller
            self.initial = initial
            self.state = state
            self.cancelID = cancelID
            self.guardEdits = guardEdits
            self.dismissible = dismissible
            self.discard = discard
            self.completion = completion
        }

        var dirty: Bool { guardEdits && state?.snapshot.sections != initial?.sections }
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
                    if row.id == cancelID { self?.finish(id: id, action: nil, reason: "cancel") }
                    else { self?.finish(id: id, action: row.id, reason: "action") }
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
                    self.requestDismissal(active, reason: "cancel")
                } else if snapshot.toolbar.contains(where: { $0.id == rowID && $0.enabled }) {
                    self.finish(id: id, action: rowID, reason: "action")
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
        let presentation = Presentation(id: id, controller: controller, initial: snapshot, state: state,
                                        cancelID: cancelID, guardEdits: args["guardEdits"] as? Bool == true,
                                        dismissible: args["dismissible"] as? Bool != false,
                                        discard: discard, completion: completion)
        active = presentation
        show(presentation, from: parent)
        // UIAlertController owns its presentation delegate. Editable sheets use ours to guard drafts.
        if state != nil { controller.presentationController?.delegate = self }
    }

    /// Presents a blocking activity in the same single slot. It ends only through `dismiss(id:)`, or
    /// when UIKit fails to show it or another owner removes it ('dismissed').
    func presentActivity(_ input: Any?, completion: @escaping (Any?) -> Void) throws {
        guard active == nil else { throw PresentationError.unavailable }
        let request = try NativeActivityRequest.decode(input)
        guard var parent = rootController() else { throw PresentationError.unavailable }
        while let presented = parent.presentedViewController { parent = presented }
        guard parent.viewIfLoaded?.window != nil, !parent.isBeingDismissed else {
            throw PresentationError.unavailable
        }
        let controller = UIHostingController(rootView: NativeActivityView(request: request))
        controller.view.backgroundColor = .clear
        controller.view.accessibilityViewIsModal = true
        controller.modalPresentationStyle = .overFullScreen
        controller.modalTransitionStyle = .crossDissolve
        controller.isModalInPresentation = true
        controller.overrideUserInterfaceStyle = request.appearance == "system" ? .unspecified
            : request.appearance == "dark" ? .dark : .light
        let presentation = Presentation(id: request.id, controller: controller, initial: nil, state: nil,
                                        cancelID: "", guardEdits: false, dismissible: false, discard: [:],
                                        completion: completion)
        active = presentation
        show(presentation, from: parent, announcing: request.label)
    }

    func dismiss(id: Int) { finish(id: id, action: nil, reason: "programmatic") }

    private func show(_ presentation: Presentation, from parent: UIViewController, announcing label: String? = nil) {
        parent.present(presentation.controller, animated: true) { [weak self] in
            presentation.shown = true
            if let label, self?.active === presentation {
                UIAccessibility.post(notification: .announcement, argument: label)
            }
            presentation.whenShown?()
            presentation.whenShown = nil
        }
        watch(presentation)
    }

    /// UIKit can fail to show a presentation, and another owner can dismiss it without telling this
    /// presenter. Either way nothing presents it any more, so it ends as 'dismissed' and the slot,
    /// and Dart's presentation order behind it, moves on.
    private func watch(_ presentation: Presentation) {
        presentation.monitor = Task { [weak self, weak presentation] in
            var missing = 0
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 500_000_000)
                guard let self, let presentation, self.active === presentation else { return }
                let controller = presentation.controller
                missing = controller.presentingViewController == nil && !controller.isBeingPresented ? missing + 1 : 0
                // Two checks in a row, so a system alert closing for its own action reports that action.
                if missing == 2 { self.release(presentation, reason: "dismissed") }
            }
        }
    }

    private func finish(id: Int, action: String?, reason: String) {
        guard let presentation = active, presentation.id == id else { return }
        var values: [String: Any] = [:]
        if action != nil, let snapshot = presentation.state?.snapshot ?? presentation.initial {
            values = Dictionary(snapshot.sections.flatMap(\.rows).compactMap { row -> (String, Any)? in
                switch row.value {
                case let .text(text): return (row.id, text)
                case let .bool(flag): return (row.id, flag)
                case let .number(number): return (row.id, number)
                case nil: return nil
                }
            }, uniquingKeysWith: { _, latest in latest })
        }
        presentation.state?.invalidate()
        presentation.monitor?.cancel()
        active = nil
        let outcome = Self.outcome(action: action, values: values, reason: reason)
        let controller = presentation.controller
        if presentation.shown { Self.close(presentation, outcome) }
        else if controller.presentingViewController == nil, !controller.isBeingPresented {
            // UIKit never showed it, so nothing is left to close; should it still appear, it goes at once.
            presentation.whenShown = { controller.presentingViewController?.dismiss(animated: false) }
            presentation.completion(outcome)
        } else { presentation.whenShown = { Self.close(presentation, outcome) } }
    }

    /// Ends a presentation that already left the screen without this presenter.
    private func release(_ presentation: Presentation, reason: String) {
        guard active === presentation else { return }
        presentation.state?.invalidate()
        presentation.monitor?.cancel()
        active = nil
        // Should UIKit still show one it failed to present, it does not stay up untracked.
        if !presentation.shown {
            let controller = presentation.controller
            presentation.whenShown = { controller.presentingViewController?.dismiss(animated: false) }
        }
        presentation.completion(Self.outcome(action: nil, values: [:], reason: reason))
    }

    /// Dismisses from the presenting controller, so a discard confirmation above a sheet closes with it.
    private static func close(_ presentation: Presentation, _ outcome: [String: Any]) {
        let controller = presentation.controller
        guard let presenter = controller.presentingViewController else {
            // Already off screen: a system alert after its own action, or one another owner removed.
            presentation.completion(outcome)
            return
        }
        if controller.isBeingDismissed {
            let queued = controller.transitionCoordinator?.animate(alongsideTransition: nil) { _ in
                presentation.completion(outcome)
            }
            if queued != true { presentation.completion(outcome) }
            return
        }
        presenter.dismiss(animated: true) { presentation.completion(outcome) }
    }

    /// Values cross only with an action; an absent action is omitted rather than sent as null.
    private static func outcome(action: String?, values: [String: Any], reason: String) -> [String: Any] {
        var outcome: [String: Any] = ["values": values, "reason": reason]
        if let action { outcome["action"] = action }
        return outcome
    }

    private func requestDismissal(_ presentation: Presentation, reason: String) {
        guard presentation.dirty else { finish(id: presentation.id, action: nil, reason: reason); return }
        guard !presentation.asking else { return }
        presentation.asking = true
        let alert = UIAlertController(title: presentation.discard["title"],
                                      message: presentation.discard["message"], preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: presentation.discard["cancel"], style: .cancel) { _ in
            presentation.asking = false
        })
        alert.addAction(UIAlertAction(title: presentation.discard["confirm"], style: .destructive) { [weak self] _ in
            presentation.asking = false
            self?.finish(id: presentation.id, action: nil, reason: reason)
        })
        presentation.controller.present(alert, animated: true)
    }

    func presentationControllerShouldDismiss(_ presentationController: UIPresentationController) -> Bool {
        !(active?.dirty ?? false)
    }

    func presentationControllerDidAttemptToDismiss(_ presentationController: UIPresentationController) {
        if let active, active.dismissible { requestDismissal(active, reason: "dismissed") }
    }

    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        guard let presentation = active, presentationController.presentedViewController === presentation.controller
        else { return }
        release(presentation, reason: "dismissed")
    }

    enum PresentationError: Error { case invalid, unavailable }
}

/// A blocking activity: the content beneath is dimmed and inert, and a card shows the owner's label.
@available(iOS 16.0, *)
struct NativeActivityView: View {
    let request: NativeActivityRequest

    var body: some View {
        ZStack {
            Color.black.opacity(0.25).ignoresSafeArea()
            // Large text keeps the whole label reachable instead of clipping it.
            ViewThatFits(in: .vertical) {
                card
                ScrollView { card.padding(.vertical, 24) }
            }
            .padding(24)
        }
        .contentShape(Rectangle())
        .environment(\.locale, Locale(identifier: request.locale))
        .environment(\.layoutDirection, request.direction == "rtl" ? .rightToLeft : .leftToRight)
        .accessibilityAddTraits(.isModal)
    }

    private var card: some View {
        ProgressView {
            Text(request.label).font(.headline).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .controlSize(.large)
        .padding(24)
        .frame(minWidth: 160, maxWidth: 320)
        .modifier(NativeActivityCardStyle())
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("native-activity")
    }
}

private struct NativeActivityCardStyle: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular, in: .rect(cornerRadius: 24))
        } else {
            content.background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        }
    }
}
