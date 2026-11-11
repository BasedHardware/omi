import OmiTheme
import SwiftUI

/// "What you get" — the concrete case for one integration, rendered from the
/// same catalog the proactive nudge reads.
///
/// Before this existed, a connector sheet said one line ("Import email history
/// and follow-ups") and then showed a Connect button. That is a description of
/// a mechanism, not a reason. This section names three things the user can do
/// afterwards that they cannot do now, and states plainly what Omi reads — so
/// the decision is informed from either entry point, the Apps tab or a nudge.
struct IntegrationValueSection: View {
  let entry: IntegrationNudgeCatalogEntry

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text("What you get")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .textCase(.uppercase)

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(entry.useCases, id: \.self) { useCase in
          HStack(alignment: .top, spacing: OmiSpacing.xs) {
            Image(systemName: "checkmark")
              .font(.system(size: 10, weight: .bold))
              .foregroundColor(Ink.secondary)
              .padding(.top, 3)

            Text(useCase)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.primary)
              .fixedSize(horizontal: false, vertical: true)
              .multilineTextAlignment(.leading)
          }
        }
      }

      HStack(alignment: .top, spacing: OmiSpacing.xs) {
        Image(systemName: "lock.shield")
          .font(.system(size: 10, weight: .semibold))
          .foregroundColor(Ink.secondary)
          .padding(.top, 2)

        Text(entry.dataScope)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .multilineTextAlignment(.leading)
      }
      .padding(.top, OmiSpacing.xxs)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
