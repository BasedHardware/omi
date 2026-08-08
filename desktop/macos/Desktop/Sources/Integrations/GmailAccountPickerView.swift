import OmiTheme
import SwiftUI

struct GmailAccountPickerView: View {
  let accounts: [GmailAccountOption]
  let selectedCookiePath: String?
  let onSelect: (String?, String) -> Void
  let onCancel: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("Gmail account")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        Button("Cancel", action: onCancel)
          .buttonStyle(.plain)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(Ink.secondary)
      }

      Button {
        onSelect(nil, "Automatic")
      } label: {
        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text("Automatic")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
            Text("First readable browser account")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.tertiary)
          }
          Spacer()
          if selectedCookiePath == nil {
            Image(systemName: "checkmark")
              .foregroundColor(Ink.accent)
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
                .foregroundColor(Ink.primary)
              Text(account.email ?? "Unknown account")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.tertiary)
            }
            Spacer()
            if selectedCookiePath == account.id {
              Image(systemName: "checkmark")
                .foregroundColor(Ink.accent)
            }
          }
        }
        .buttonStyle(.plain)
      }
    }
    .padding(OmiSpacing.lg)
    .frame(width: 400)
    .background(Ink.surface)
  }

  private func accountLabel(_ account: GmailAccountOption) -> String {
    account.email.map { "\($0) (\(account.browserName))" } ?? account.browserName
  }
}
