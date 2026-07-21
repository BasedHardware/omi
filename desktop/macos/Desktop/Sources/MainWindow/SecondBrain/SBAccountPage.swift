import OmiTheme
import SwiftUI

/// Native Second Brain "Account & Billing" — coherent with the rest of the UI.
/// Real: name, email, sign out. Manage and Delete both open the legacy Account &
/// Billing section, which holds the working plan controls and the delete-account
/// confirmation alert (one tap away). Auto-opening the destructive alert directly
/// is deferred to the legacy-settings blend-in work.
struct SBAccountPage: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appState: AppState
  @ObservedObject private var authState = AuthState.shared
  var onBack: () -> Void
  var onManagePlan: () -> Void
  var onDelete: () -> Void

  private var name: String {
    let n = AuthService.shared.displayName.trimmingCharacters(in: .whitespaces)
    return n.isEmpty ? "Signed in" : n
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        Button(action: onBack) {
          Text("← Settings").geist(size: 13).foregroundStyle(sb.ink(.w4))
        }
        .buttonStyle(.plain)
        .padding(.bottom, 12)

        Text("Account & Billing")
          .geist(size: 22, weight: .semibold, tracking: 22 * -0.02).foregroundStyle(sb.ink)
        Text("Your plan and data, in plain words.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w4)).padding(.bottom, 14)

        SBHairlineRow(title: name, subtitle: authState.userEmail ?? "") {
          Button {
            Task { try? await AuthService.shared.signOut() }
          } label: {
            Text("Sign out").geistMono(size: 12.5).foregroundStyle(sb.ink(.w6)).underline()
          }
          .buttonStyle(.plain)
        }

        SBHairlineRow(title: "Plan", subtitle: "your subscription and usage") {
          Button(action: onManagePlan) {
            Text("Manage").geistMono(size: 12.5).foregroundStyle(sb.ink(.w6)).underline()
          }
          .buttonStyle(.plain)
        }

        SBHairlineRow(
          title: "Delete account & all data", subtitle: "everything, everywhere, forever",
          titleToken: .w9
        ) {
          Button(action: onDelete) {
            Text("Delete…").geistMono(size: 12.5).foregroundStyle(sb.ink(.w6)).underline()
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, 30).padding(.top, 4).padding(.bottom, 24)
    }
  }
}
