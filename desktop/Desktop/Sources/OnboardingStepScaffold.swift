import AppKit
import SwiftUI

enum OnboardingRightPaneMode {
  case graph
  case message(title: String, detail: String)
}

enum OnboardingLayoutMode {
  case split
  case centered
}

struct OnboardingStepScaffold<Content: View>: View {
  @ObservedObject private var graphViewModel: MemoryGraphViewModel

  let stepIndex: Int
  let totalSteps: Int
  let eyebrow: String
  let title: String
  let description: String
  let layoutMode: OnboardingLayoutMode
  let rightPaneMode: OnboardingRightPaneMode
  let showsSkip: Bool
  let onSkip: (() -> Void)?
  let content: Content

  init(
    graphViewModel: MemoryGraphViewModel,
    stepIndex: Int,
    totalSteps: Int,
    eyebrow: String,
    title: String,
    description: String,
    layoutMode: OnboardingLayoutMode = .split,
    rightPaneMode: OnboardingRightPaneMode = .graph,
    showsSkip: Bool = false,
    onSkip: (() -> Void)? = nil,
    @ViewBuilder content: () -> Content
  ) {
    _graphViewModel = ObservedObject(wrappedValue: graphViewModel)
    self.stepIndex = stepIndex
    self.totalSteps = totalSteps
    self.eyebrow = eyebrow
    self.title = title
    self.description = description
    self.layoutMode = layoutMode
    self.rightPaneMode = rightPaneMode
    self.showsSkip = showsSkip
    self.onSkip = onSkip
    self.content = content()
  }

  var body: some View {
    switch layoutMode {
    case .split:
      HStack(spacing: 0) {
        splitPane
          .frame(minWidth: 470, idealWidth: 520, maxWidth: 560)

        Divider()
          .background(OmiColors.backgroundTertiary)

        OnboardingSecondBrainPane(graphViewModel: graphViewModel, mode: rightPaneMode)
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(OmiColors.backgroundPrimary)

    case .centered:
      VStack(spacing: 0) {
        header

        Divider()
          .background(OmiColors.backgroundTertiary)

        GeometryReader { geometry in
          ScrollView(showsIndicators: false) {
            VStack(spacing: 28) {
              progressRow(centered: true)
              titleBlock(centered: true)
              content
            }
            .frame(maxWidth: 560)
            .frame(
              minWidth: 0, maxWidth: .infinity, minHeight: geometry.size.height,
              maxHeight: .infinity, alignment: .center
            )
            .padding(.horizontal, 40)
            .padding(.vertical, 36)
          }
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(OmiColors.backgroundPrimary)
    }
  }

  private var splitPane: some View {
    VStack(spacing: 0) {
      header

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: 28) {
          progressRow(centered: false)
          titleBlock(centered: false)
          content
        }
        .frame(maxWidth: 500, alignment: .leading)
        .padding(.horizontal, 40)
        .padding(.vertical, 36)
      }
    }
    .background(OmiColors.backgroundPrimary)
  }

  private var header: some View {
    HStack {
      if let logoImage = onboardingLogoImage() {
        Image(nsImage: logoImage)
          .resizable()
          .renderingMode(.template)
          .foregroundColor(.white)
          .scaledToFit()
          .frame(width: 52, height: 18)
          .accessibilityLabel("omi")
      } else {
        Text("omi")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(.white)
      }

      Spacer()

      if showsSkip, let onSkip {
        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 24)
    .padding(.vertical, 16)
  }

  private func progressRow(centered: Bool) -> some View {
    HStack(spacing: 8) {
      ForEach(0..<totalSteps, id: \.self) { index in
        Capsule()
          .fill(index <= stepIndex ? OmiColors.purplePrimary : Color.white.opacity(0.1))
          .frame(width: index == stepIndex ? 28 : 8, height: 6)
      }
    }
    .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
  }

  private func titleBlock(centered: Bool) -> some View {
    VStack(alignment: centered ? .center : .leading, spacing: 14) {
      Text(eyebrow.uppercased())
        .font(.system(size: 12, weight: .semibold))
        .tracking(1.2)
        .foregroundColor(OmiColors.purplePrimary)

      Text(title)
        .font(.system(size: 40, weight: .bold))
        .foregroundColor(OmiColors.textPrimary)
        .lineSpacing(2)
        .multilineTextAlignment(centered ? .center : .leading)

      Text(description)
        .font(.system(size: 16))
        .foregroundColor(OmiColors.textSecondary)
        .lineSpacing(4)
        .multilineTextAlignment(centered ? .center : .leading)
        .frame(maxWidth: 460, alignment: centered ? .center : .leading)
    }
    .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
  }

  private func onboardingLogoImage() -> NSImage? {
    guard
      let logoURL = Bundle.resourceBundle.url(forResource: "omi_text_logo", withExtension: "png"),
      let loadedLogoImage = NSImage(contentsOf: logoURL)
    else {
      return nil
    }
    let logoImage = loadedLogoImage.copy() as? NSImage ?? loadedLogoImage
    logoImage.isTemplate = true
    return logoImage
  }
}

private struct OnboardingSecondBrainPane: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let mode: OnboardingRightPaneMode

  var body: some View {
    ZStack {
      OmiColors.backgroundSecondary
        .ignoresSafeArea()

      switch mode {
      case .message(let title, let detail):
        VStack(spacing: 12) {
          Text(title)
            .font(.system(size: 28, weight: .bold))
            .foregroundColor(OmiColors.textPrimary)
            .multilineTextAlignment(.center)

          Text(detail)
            .font(.system(size: 15))
            .foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 320)
        }
      case .graph:
        if graphViewModel.isEmpty {
          VStack(spacing: 14) {
            Text("Your graph appears once Omi has something real to map.")
              .font(.system(size: 15, weight: .medium))
              .foregroundColor(OmiColors.textTertiary)
              .multilineTextAlignment(.center)
              .frame(maxWidth: 320)
          }
        } else {
          MemoryGraphSceneView(viewModel: graphViewModel)
            .ignoresSafeArea()
        }
      }
    }
    .overlay(alignment: .top) {
      if case .graph = mode, !graphViewModel.isEmpty {
        Text("This is your second brain.")
          .font(.system(size: 14, weight: .semibold))
          .foregroundColor(.white)
          .padding(.horizontal, 12)
          .padding(.vertical, 6)
          .background(Color.black.opacity(0.35))
          .cornerRadius(8)
          .padding(.top, 18)
      }
    }
    .overlay(alignment: .bottom) {
      if case .graph = mode, !graphViewModel.isEmpty {
        HStack(spacing: 20) {
          graphHintItem(icon: "arrow.triangle.2.circlepath", label: "Drag to rotate")
          graphHintItem(icon: "magnifyingglass", label: "Scroll to zoom")
          graphHintItem(icon: "hand.draw", label: "Two-finger to pan")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
          LinearGradient(
            colors: [Color.black.opacity(0), Color.black.opacity(0.5)],
            startPoint: .top,
            endPoint: .bottom
          )
        )
      }
    }
    .task {
      await graphViewModel.addGraphFromStorage()
      if graphViewModel.isEmpty {
        await graphViewModel.loadGraph()
      }
    }
  }

  private func graphHintItem(icon: String, label: String) -> some View {
    HStack(spacing: 4) {
      Image(systemName: icon)
        .font(.system(size: 11))
      Text(label)
        .font(.system(size: 11))
    }
    .foregroundColor(.white.opacity(0.5))
  }
}

struct OnboardingCardButtonStyle: ButtonStyle {
  let isPrimary: Bool

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.system(size: 15, weight: .semibold))
      .foregroundColor(isPrimary ? .white : OmiColors.textPrimary)
      .padding(.horizontal, 18)
      .padding(.vertical, 12)
      .background(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .fill(isPrimary ? OmiColors.purplePrimary : OmiColors.backgroundTertiary)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(Color.white.opacity(isPrimary ? 0 : 0.08), lineWidth: 1)
      )
      .opacity(configuration.isPressed ? 0.92 : 1)
      .scaleEffect(configuration.isPressed ? 0.985 : 1)
      .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
  }
}

struct OnboardingInsightCard: View {
  let icon: String
  let title: String
  let detail: String

  var body: some View {
    HStack(alignment: .top, spacing: 14) {
      ZStack {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .fill(OmiColors.backgroundQuaternary)
          .frame(width: 42, height: 42)

        Image(systemName: icon)
          .font(.system(size: 16, weight: .semibold))
          .foregroundColor(OmiColors.purplePrimary)
      }

      VStack(alignment: .leading, spacing: 6) {
        Text(title)
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)

        Text(detail)
          .font(.system(size: 13))
          .foregroundColor(OmiColors.textTertiary)
          .lineSpacing(3)
      }

      Spacer()
    }
    .padding(18)
    .background(
      RoundedRectangle(cornerRadius: 20, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: 20, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    )
  }
}

struct OnboardingSelectableChip: View {
  let title: String
  let isSelected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(isSelected ? .white : OmiColors.textSecondary)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
          Capsule()
            .fill(isSelected ? OmiColors.purplePrimary : OmiColors.backgroundSecondary)
        )
        .overlay(
          Capsule()
            .stroke(Color.white.opacity(isSelected ? 0 : 0.08), lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}
