import OmiTheme
import SwiftUI

struct GmailAccountPickerView: View {
  let accounts: [GmailAccountOption]
  let selectedCookiePath: String?
  let hasMadeChoice: Bool
  let onSelect: (String?, String) -> Void
  let onCancel: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("Gmail account")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        Button("Cancel", action: onCancel)
          .buttonStyle(.plain)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(OmiColors.textSecondary)
      }

      Button {
        onSelect(nil, "Automatic")
      } label: {
        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text("Automatic")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
            Text("First readable browser account")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          // Only an explicit choice may show the checkmark: before any
          // selection, selectedCookiePath is nil but the user has not chosen
          // Automatic, and showing it as pre-selected invites a dismiss that
          // would strand the onboarding wait.
          if hasMadeChoice && selectedCookiePath == nil {
            Image(systemName: "checkmark")
              .foregroundColor(OmiColors.accent)
          }
        }
      }
      .buttonStyle(.plain)

      Divider()

      ForEach(accounts) { account in
        Button {
          onSelect(account.id, accountLabel(account))
        } label: {
          HStack {
            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text(account.browserName)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
              Text(account.email ?? "Unknown account")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
            Spacer()
            if selectedCookiePath == account.id {
              Image(systemName: "checkmark")
                .foregroundColor(OmiColors.accent)
            }
          }
        }
        .buttonStyle(.plain)
      }
    }
    .padding(OmiSpacing.lg)
    .frame(width: 400)
    .background(OmiColors.backgroundPrimary)
  }

  private func accountLabel(_ account: GmailAccountOption) -> String {
    account.email.map { "\($0) (\(account.browserName))" } ?? account.browserName
  }
}
