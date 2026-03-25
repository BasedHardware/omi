import SwiftUI

struct OnboardingResearchStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Second Brain",
      title: "Your graph is live.",
      description: "Omi now has real context."
    ) {
      VStack(alignment: .leading, spacing: 14) {
        if let snapshot = coordinator.scanSnapshot, !snapshot.projectNames.isEmpty {
          OnboardingInsightCard(
            icon: "shippingbox.fill",
            title: "From your machine",
            detail: snapshot.projectNames.prefix(3).joined(separator: ", ")
          )
        }

        if let email = coordinator.userEmail() {
          OnboardingInsightCard(
            icon: "at",
            title: "Signed in",
            detail: email
          )
        }

        if coordinator.isLoadingInsights {
          OnboardingInsightCard(
            icon: "bolt.fill",
            title: coordinator.insightStatusText.isEmpty
              ? "Collecting context" : coordinator.insightStatusText,
            detail: "This finishes before goal selection."
          )
        }

        if !coordinator.emailSummary.isEmpty {
          OnboardingInsightCard(
            icon: "envelope.fill",
            title: "From Gmail",
            detail: coordinator.emailSummary
          )
        }

        if !coordinator.calendarSummary.isEmpty {
          OnboardingInsightCard(
            icon: "calendar",
            title: "From your calendar",
            detail: coordinator.calendarSummary
          )
        }

        if !coordinator.webResearchSummary.isEmpty {
          OnboardingInsightCard(
            icon: "globe",
            title: "From the web",
            detail: coordinator.webResearchSummary
          )
        }

        if coordinator.emailSummary.isEmpty && coordinator.calendarSummary.isEmpty
          && coordinator.webResearchSummary.isEmpty,
          let organization = coordinator.organizationHint()
        {
          OnboardingInsightCard(
            icon: "building.2.fill",
            title: "Identity hint",
            detail: organization
          )
        }

        Button(coordinator.isResearchComplete ? "Continue" : "Finishing…") {
          onContinue()
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .disabled(!coordinator.isResearchComplete)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
      }
    }
  }
}
