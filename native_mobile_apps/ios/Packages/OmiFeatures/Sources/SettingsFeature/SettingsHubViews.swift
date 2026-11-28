import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The top of Settings: who is signed in, large, with email and plan on one quiet line (and
/// Upgrade on the free plan). Tapping it opens Account.
struct SettingsProfileHeader: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(SessionStore.self) private var session
    let onOpenAccount: () -> Void
    let onUpgrade: () -> Void

    var body: some View {
        let rawName = settings.displayName ?? session.displayName
        let email = settings.email
        let name = SettingsHub.headline(name: rawName, email: email) ?? L("account")
        let subscription = settings.subscription
        HStack(alignment: .center, spacing: DS.Spacing.md) {
            Button(action: onOpenAccount) {
                HStack(alignment: .center, spacing: DS.Spacing.md) {
                    Text(SettingsHub.initials(name: rawName, email: email))
                        .font(DS.Typography.sectionTitle)
                        .foregroundStyle(DS.Palette.ink)
                        .frame(width: 52, height: 52)
                        .background(DS.Palette.card, in: Circle())
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(name)
                            .font(DS.Typography.largeTitle)
                            .foregroundStyle(DS.Palette.ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        HStack(spacing: DS.Spacing.sm) {
                            if let email {
                                Text(email)
                                    .font(DS.Typography.callout)
                                    .foregroundStyle(DS.Palette.inkSecondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }
                            if let subscription {
                                Text(PlanUsageScreen.planName(subscription))
                                    .font(DS.Typography.micro)
                                    .foregroundStyle(DS.Palette.inkSecondary)
                                    .padding(.horizontal, DS.Spacing.sm)
                                    .padding(.vertical, 3)
                                    .background(DS.Palette.fill, in: Capsule())
                                    .fixedSize()
                            }
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            .accessibilityHint(L("account"))
            .accessibilityIdentifier("settings.account")
            if let subscription, SettingsHub.isFree(subscription), subscription.showSubscriptionUI {
                Button(L("upgrade"), action: onUpgrade)
                    .buttonStyle(.omiPill)
                    .fixedSize()
                    .accessibilityIdentifier("settings.upgrade")
            }
        }
        .padding(.top, DS.Spacing.xs)
        .padding(.bottom, DS.Spacing.lg)
    }
}

/// Four live tiles under the header: the Omi, the plan, apps, voices. Each opens its screen.
struct SettingsHubTiles: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(DeviceStore.self) private var devices
    @Environment(CaptureStore.self) private var capture
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    @Environment(RemindersSyncStore.self) private var reminders
    let onOpen: (SettingsTopic) -> Void

    var body: some View {
        Grid(horizontalSpacing: DS.Spacing.md, verticalSpacing: DS.Spacing.md) {
            GridRow {
                omiTile
                planTile
            }
            GridRow {
                appsTile
                voicesTile
            }
        }
        .padding(.bottom, DS.Spacing.sm)
    }

    private var omiState: SettingsHub.OmiState {
        SettingsHub.omiState(
            isPaired: devices.paired != nil, connection: devices.connection, battery: devices.battery,
            isMuted: capture.isDeviceMuted, isListening: capture.source == .device && capture.isLive
        )
    }

    private var omiTile: some View {
        let state = omiState
        let value = OmiStatusText.short(state)
        return HubTile(title: devices.paired?.name ?? "Omi", accessibilityValue: value, topic: .devices, onOpen: onOpen) {
            OmiPendantThumbnail(size: 30)
                .opacity(state.isConnected ? 1 : 0.45)
                .overlay(alignment: .bottomTrailing) { OmiStatusDot(dot: state.dot) }
        } value: {
            Text(value)
        }
    }

    private var planTile: some View {
        let subscription = settings.subscription
        let meter = subscription.map(PlanCatalog.meters).flatMap(SettingsHub.busiestMeter)
        let title = subscription.map(PlanUsageScreen.planName) ?? L("nativePlan")
        let percent = meter?.fraction.map(SettingsHub.percent)
        let spoken = percent.map { L("nativeHubPercentUsed", "\($0)%") } ?? ""
        return HubTile(title: title, accessibilityValue: spoken, topic: .planUsage, onOpen: onOpen) {
            HubGlyph(systemImage: "chart.bar")
        } value: {
            if let meter, let fraction = meter.fraction, let percent {
                HStack(spacing: DS.Spacing.sm) {
                    OmiMeterBar(fraction: fraction, tint: Self.tint(meter)).frame(maxWidth: 72)
                    Text(verbatim: "\(percent)%").monospacedDigit()
                }
            } else {
                Text(L("nativeSettingsPlanUsage"))
            }
        }
    }

    private var appsTile: some View {
        let count = SettingsHub.connectedApps(capabilities.integrations, health: health.isConnected, reminders: reminders.isEnabled)
        let value = count == 0 ? L("nativeHubConnectApps") : L("nativeHubConnectedCount", String(count))
        return HubTile(title: L("nativeHubApps"), accessibilityValue: value, topic: .apps, onOpen: onOpen) {
            HubGlyph(systemImage: "square.grid.2x2")
        } value: {
            Text(value)
        }
    }

    private var voicesTile: some View {
        let count = settings.people.count
        let value = switch count {
        case 0: L("nativeHubNoPeople")
        case 1: L("nativeHubOnePerson")
        default: L("nativeHubPeopleCount", String(count))
        }
        return HubTile(title: L("nativeHubVoices"), accessibilityValue: value, topic: .voices, onOpen: onOpen) {
            HubGlyph(systemImage: "person.2")
        } value: {
            Text(value)
        }
    }

    /// Ink, amber near the limit, red at it (as on Plan & usage).
    private static func tint(_ meter: UsageMeter) -> Color {
        meter.isAtLimit ? DS.Palette.live : meter.isNearLimit ? DS.Palette.warning : DS.Palette.ink
    }
}

/// One tile: a thin glyph on top, the title, one live line under it, on the raised card color.
private struct HubTile<Glyph: View, Value: View>: View {
    let title: String
    let accessibilityValue: String
    let topic: SettingsTopic
    let onOpen: (SettingsTopic) -> Void
    @ViewBuilder let glyph: Glyph
    @ViewBuilder let value: Value

    var body: some View {
        Button {
            onOpen(topic)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                glyph.frame(height: 30, alignment: .leading)
                Spacer(minLength: DS.Spacing.md)
                Text(title)
                    .font(DS.Typography.body.weight(.semibold))
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(1)
                value
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
                    .frame(height: 20, alignment: .leading)
                    .padding(.top, DS.Spacing.xxs)
            }
            .padding(DS.Spacing.lg)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .frame(minHeight: 112)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
        }
        .buttonStyle(TilePressStyle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(accessibilityValue))
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("settings.\(topic.rawValue)")
    }
}

/// A tile's thin line glyph.
private struct HubGlyph: View {
    let systemImage: String

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: 21, weight: .light))
            .foregroundStyle(DS.Palette.ink)
            .accessibilityHidden(true)
    }
}

/// Tiles sink a little under the finger.
private struct TilePressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(DS.Motion.snappy, value: configuration.isPressed)
    }
}
