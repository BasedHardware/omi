import XCTest

@testable import Omi_Computer

/// Regression coverage for `FloatingBarNotificationPreviewPolicy` (issue #6765
/// plus the bar-disabled temp-show contract).
///
/// Only the Notifications master toggle (and frequency gate in
/// `NotificationService`) decide whether a notification is owed. The Ask Omi
/// enable toggle controls persistent bar UI only: a disabled bar still presents
/// via temp-show, then re-hides. Muting in-bar previews while the bar stays
/// enabled is the one case that falls back to a native system banner so the
/// notification is never fully silenced.
final class FloatingBarNotificationPreviewPolicyTests: XCTestCase {
  /// Runtime owner authorization is process-wide and fails closed on an
  /// out-of-band `authUserId` write, staying revoked for every later suite in
  /// the xctest process. The two owner-seeding tests below therefore establish
  /// their owner through the production transition boundary, and restore runs
  /// in `tearDown` rather than a `defer` so a failed assertion cannot leave the
  /// authority revoked for whatever runs next.
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    ownerFixture = await RuntimeOwnerAuthorityTestFixture()
  }

  override func tearDown() async throws {
    await ownerFixture?.restore()
    ownerFixture = nil
  }

  func testPreviewsAndBarEnabledShowsPreviewWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: false))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledPresentsViaTempShowWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false),
      "bar disabled + notifications owed must still present the in-bar card via temp-show")
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false),
      "disabling the bar must not force a contentless system banner")
  }

  func testPreviewsMutedSkipsPreviewAndFallsBackToBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledAndPreviewsMutedStillTempShowsTheCard() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: false),
      "previews muted + bar disabled must still temp-show the card; only the notification toggle silences")
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: false),
      "the combined muted+disabled case uses the card, not a system banner")
  }

  func testBarDisabledDoesNotSilenceWhenMasterNotificationsAreOffTheMasterGateDoes() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false))
    XCTAssertEqual(
      InsightAssistantTelemetry.Reason.masterNotificationsDisabled.rawValue,
      "master_notifications_disabled",
      "bar disabled + notifications off is suppressed by NotificationService's master toggle, not by preview policy")
  }

  func testExplicitSystemBannerAlwaysDeliversRegardlessOfPreviewState() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: true))
  }

  func testExplicitBannerDoesNotDuplicateAnAcceptedFloatingBarPresentation() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: true,
        deliverSystemBanner: true,
        floatingBarAccepted: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: true,
        deliverSystemBanner: true,
        floatingBarAccepted: false))
  }

  /// A functional caller (`deliverSystemBanner: true`) with the bar disabled must keep the
  /// persistent banner it asked for. Routing it through the temp-show card marks the
  /// floating bar as having accepted delivery, which suppresses the banner — and the
  /// screen-recording repair notice is one-per-episode, so the seconds-long card is the
  /// only notice the user ever gets while capture stays broken.
  func testFunctionalBannerWithBarDisabledKeepsItsBannerInsteadOfTheTempShowCard() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: true),
      "a functional notice with the bar disabled must not be swallowed by the temp-show card")
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: false,
        deliverSystemBanner: true,
        floatingBarAccepted: false),
      "skipping the card must leave the explicit system banner as the delivered surface")
  }

  /// The muted-previews variant of the same case: still no card, still the banner.
  func testFunctionalBannerWithBarDisabledAndPreviewsMutedStillDeliversTheBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: false,
        floatingBarEnabled: false,
        deliverSystemBanner: true,
        floatingBarAccepted: false))
  }

  /// The bar-enabled contract is untouched: the card stays authoritative and an explicit
  /// banner request does not duplicate it.
  func testFunctionalBannerWithBarEnabledStillPresentsTheCardAndNoDuplicateBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: true))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: true,
        deliverSystemBanner: true,
        floatingBarAccepted: true))
  }

  /// Proactive delivery with the bar disabled keeps the temp-show card (the #11636 fix).
  func testProactiveDeliveryWithBarDisabledStillUsesTheTempShowCard() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: false,
        deliverSystemBanner: false,
        floatingBarAccepted: true))
  }

  func testDirectorMutedPreviewFallsBackToBannerInsteadOfSilentQuotaBurn() {
    // Context-director presentation must use this policy: muted previews with
    // the floating bar still enabled keep a visible system-banner surface.
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false),
      "muted in-bar preview must keep a banner surface so director delivery is visible")
  }

  func testMutedJITNoticeUsesSystemBannerUntilTheUserTapsIt() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false,
        floatingBarEnabled: true,
        deliverSystemBanner: false),
      "a muted preview must not bypass the user's preference for JIT feedback")
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false),
      "the muted JIT preview still owes a visible system-banner surface")
  }

  @MainActor
  func testTappedMutedJITBannerRoutesOpaqueContextToPersistentFeedbackDetail() throws {
    let context = JITTriggerFeedbackContext(
      ownerID: "owner-jit-banner",
      eventID: JITProactivityReservation.identifier("event", "jit-banner"),
      triggerMemoryID: "memory-jit-banner",
      accountGeneration: 4,
      triggerRevision: 7)
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: "context-director",
        title: "A useful reminder",
        jitFeedbackContext: context),
      .openJITDetail,
      "a tapped JIT system banner must open the detail card, not only record analytics")

    let userInfo: [AnyHashable: Any] = [
      "omi.jit.feedback.v1": [
        "owner_id": context.ownerID,
        "event_id": context.eventID,
        "trigger_memory_id": context.triggerMemoryID,
        "account_generation": context.accountGeneration,
        "trigger_revision": context.triggerRevision,
      ]
    ]
    XCTAssertEqual(
      NotificationService.jitFeedbackContext(from: userInfo),
      context,
      "the system banner must carry only the opaque, owner-fenced feedback join keys")
    XCTAssertEqual(
      JITTriggerFeedbackActionRouter.visibleActions,
      [.useful, .falsePositive, .snooze, .disable, .missedOrLate],
      "the persistent detail route must retain every explicit feedback action")
  }

  @MainActor
  func testSystemBannerTapPresentsOwnerFencedPersistentJITCardWithAllActions() throws {
    let defaults = UserDefaults.standard
    let authKey = DefaultsKey.authUserId.rawValue
    let overrideKey = DefaultsKey.automationOwnerOverride.rawValue
    let priorAuth = defaults.object(forKey: authKey)
    let priorOverride = defaults.object(forKey: overrideKey)
    let priorOwner = RuntimeOwnerIdentity.currentOwnerId()
    let owner = "owner-jit-banner-route-\(UUID().uuidString)"
    defer {
      if let priorAuth { defaults.set(priorAuth, forKey: authKey) } else { defaults.removeObject(forKey: authKey) }
      if let priorOverride {
        defaults.set(priorOverride, forKey: overrideKey)
      } else {
        defaults.removeObject(forKey: overrideKey)
      }
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: priorOwner)
    }

    defaults.set(owner, forKey: authKey)
    defaults.removeObject(forKey: overrideKey)
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: owner)
    let context = JITTriggerFeedbackContext(
      ownerID: owner,
      eventID: JITProactivityReservation.identifier("event", "jit-banner-route"),
      triggerMemoryID: "memory-jit-banner-route",
      accountGeneration: AccountCutoverControlManager.shared.control.accountGeneration,
      triggerRevision: 9)
    let userInfo: [AnyHashable: Any] = [
      "omi.jit.feedback.v1": [
        "owner_id": context.ownerID,
        "event_id": context.eventID,
        "trigger_memory_id": context.triggerMemoryID,
        "account_generation": context.accountGeneration,
        "trigger_revision": context.triggerRevision,
      ]
    ]
    var presented: (String, String, String, JITTriggerFeedbackContext, Bool)?
    let service = NotificationService(
      registerWithSystemNotificationCenter: false,
      jitDetailPresenter: { ownerID, title, message, _, feedbackContext, _, isPersistent in
        presented = (
          ownerID,
          title,
          message,
          feedbackContext,
          isPersistent
        )
      })

    XCTAssertTrue(
      service.routeJITDetailCard(
        title: "A useful reminder",
        message: "The release is waiting on review.",
        userInfo: userInfo))
    XCTAssertEqual(presented?.0, owner)
    XCTAssertEqual(presented?.1, "A useful reminder")
    XCTAssertEqual(presented?.2, "The release is waiting on review.")
    XCTAssertEqual(presented?.3, context)
    XCTAssertEqual(presented?.4, true)
    XCTAssertEqual(
      JITTriggerFeedbackActionRouter.visibleActions,
      [.useful, .falsePositive, .snooze, .disable, .missedOrLate])

    // A still-valid owner snapshot cannot authorize a banner from another
    // cutover generation. Exercise the same presenter path as the positive.
    var stalePayload = try XCTUnwrap(userInfo["omi.jit.feedback.v1"] as? [String: Any])
    stalePayload["account_generation"] = context.accountGeneration + 1
    presented = nil
    XCTAssertFalse(
      service.routeJITDetailCard(
        title: "A useful reminder",
        message: "The release is waiting on review.",
        userInfo: ["omi.jit.feedback.v1": stalePayload]))
    XCTAssertNil(presented)
  }

  @MainActor
  func testDirectorRejectsStaleJITGenerationBeforePresentation() async throws {
    let owner = "owner-jit-generation-gate-\(UUID().uuidString)"
    let fixture = try XCTUnwrap(ownerFixture)
    await fixture.establish(authOwnerID: owner)
    let currentGeneration = AccountCutoverControlManager.shared.control.accountGeneration
    let candidateID = JITProactivityReservation.identifier("candidate", "stale-generation")
    let eventID = JITProactivityReservation.identifier("notification", candidateID)
    let context = JITAmbientFeedbackContext(
      ownerID: owner,
      eventID: eventID,
      candidateID: candidateID,
      accountGeneration: currentGeneration + 1,
      authorizationGeneration: 0,
      authorizationNonce: UUID(uuidString: "00000000-0000-0000-0000-000000000201") ?? UUID())
    var droppedCount = 0
    let service = NotificationService(registerWithSystemNotificationCenter: false)

    let result = service.presentContextDirectorNotification(
      ownerID: owner,
      title: "Stale ambient card",
      message: "This card must not cross a cutover.",
      decisionType: "suggest",
      context: FloatingBarNotificationContext(
        sourceTitle: "Context director",
        assistantId: "context-director"),
      jitAmbientFeedbackContext: context,
      onDropped: { droppedCount += 1 })

    XCTAssertEqual(result, .suppressed)
    XCTAssertEqual(droppedCount, 1)
  }

  /// Behavioral guard for the category taxonomy: the director's real entry point must
  /// refuse a delivery whose category toggle is off. A "suggest" decision is a generic
  /// tip, which the taxonomy files under Insight. Every upstream gate is pinned open
  /// (owner seeded, master on, frequency Maximum, not paywalled) and the surface is
  /// pinned to the deterministic banner path (bar enabled, previews muted), so the
  /// Insight toggle is the only closed gate: removing the category guard from
  /// `presentContextDirectorNotification` makes this call return `.queued` from the
  /// banner path instead of `.suppressed`, failing the test.
  @MainActor
  func testDirectorDeliveryWithDisabledCategoryToggleIsSuppressedAtTheEntryPoint() async throws {
    let defaults = UserDefaults.standard
    let pinnedKeys = [
      NotificationService.masterEnabledDefaultsKey,
      NotificationService.frequencyDefaultsKey,
      DefaultsKey.desktopIsPaywalled.rawValue,
      DefaultsKey.askOmiBarEnabled.rawValue,
    ]
    let savedValues = pinnedKeys.map { ($0, defaults.object(forKey: $0)) }
    let savedInsightEnabled = InsightAssistantSettings.shared.notificationsEnabled
    let savedPreviewsEnabled = ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled
    defer {
      for (key, value) in savedValues {
        if let value {
          defaults.set(value, forKey: key)
        } else {
          defaults.removeObject(forKey: key)
        }
      }
      InsightAssistantSettings.shared.notificationsEnabled = savedInsightEnabled
      ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled = savedPreviewsEnabled
    }

    let owner = "owner-category-gate-\(UUID().uuidString)"
    let fixture = try XCTUnwrap(ownerFixture)
    await fixture.establish(authOwnerID: owner)
    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)
    defaults.set(false, forKey: DefaultsKey.desktopIsPaywalled.rawValue)
    defaults.set(true, forKey: DefaultsKey.askOmiBarEnabled.rawValue)
    ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled = false
    InsightAssistantSettings.shared.notificationsEnabled = false
    let liveOwner = try XCTUnwrap(RuntimeOwnerIdentity.currentOwnerId())
    XCTAssertEqual(liveOwner, owner)

    var droppedCount = 0
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let result = service.presentContextDirectorNotification(
      ownerID: liveOwner,
      title: "PR #11937 blocked",
      message: "The merge is waiting on a re-run of the flaky suite.",
      decisionType: "suggest",
      context: FloatingBarNotificationContext(
        sourceTitle: "Context director",
        assistantId: "context-director"),
      onDropped: { droppedCount += 1 })

    XCTAssertEqual(result, .suppressed)
    XCTAssertEqual(droppedCount, 1)
  }

  /// The category toggles bind every proactive producer at the shared
  /// `sendNotification` boundary — including the dedicated producers that never
  /// consulted a toggle before generating: goals (Insight) and meeting action items
  /// (Task). Same construction as the director test: every upstream gate is pinned
  /// open and the surface pinned to the banner path, so with the category gate
  /// removed these calls fall through to a delivery dispatch this bundle-less test
  /// host cannot perform, failing the test; with the gate present they return
  /// before any surface and leave the presentation ledger untouched.
  @MainActor
  func testGoalAndMeetingProducersHonorTheirCategoryTogglesAtTheSharedBoundary() async throws {
    let defaults = UserDefaults.standard
    let pinnedKeys = [
      NotificationService.masterEnabledDefaultsKey,
      NotificationService.frequencyDefaultsKey,
      DefaultsKey.desktopIsPaywalled.rawValue,
      DefaultsKey.askOmiBarEnabled.rawValue,
    ]
    let savedValues = pinnedKeys.map { ($0, defaults.object(forKey: $0)) }
    let savedInsightEnabled = InsightAssistantSettings.shared.notificationsEnabled
    let savedTaskEnabled = TaskAssistantSettings.shared.notificationsEnabled
    let savedPreviewsEnabled = ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled
    defer {
      for (key, value) in savedValues {
        if let value {
          defaults.set(value, forKey: key)
        } else {
          defaults.removeObject(forKey: key)
        }
      }
      InsightAssistantSettings.shared.notificationsEnabled = savedInsightEnabled
      TaskAssistantSettings.shared.notificationsEnabled = savedTaskEnabled
      ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled = savedPreviewsEnabled
    }

    let owner = "owner-producer-gate-\(UUID().uuidString)"
    let fixture = try XCTUnwrap(ownerFixture)
    await fixture.establish(authOwnerID: owner)
    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)
    defaults.set(false, forKey: DefaultsKey.desktopIsPaywalled.rawValue)
    defaults.set(true, forKey: DefaultsKey.askOmiBarEnabled.rawValue)
    ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled = false
    InsightAssistantSettings.shared.notificationsEnabled = false
    TaskAssistantSettings.shared.notificationsEnabled = false
    let liveOwner = try XCTUnwrap(RuntimeOwnerIdentity.currentOwnerId())
    XCTAssertEqual(liveOwner, owner)

    let service = NotificationService(registerWithSystemNotificationCenter: false)
    service.sendNotification(
      ownerID: liveOwner,
      title: "New Goal",
      message: "Ship the four-type notification taxonomy",
      assistantId: "goals")
    service.sendNotification(
      ownerID: liveOwner,
      title: "Meeting notes ready",
      message: "2 action items from standup",
      assistantId: "meeting-notes",
      deliveryMode: .systemBannerOnly)

    XCTAssertNil(
      service.lastProactivePresentationAtForCurrentOwner(),
      "a category-suppressed delivery must never advance the proactive presentation ledger")
  }

  @MainActor
  func testDirectorOwnerRefusalInvokesDroppedCallbackExactlyOnce() {
    var droppedCount = 0
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let result = service.presentContextDirectorNotification(
      ownerID: "",
      title: "Suggestion",
      message: "Do the next thing",
      decisionType: "suggestion",
      context: FloatingBarNotificationContext(
        sourceTitle: "Context director",
        assistantId: "context-director"),
      onDropped: { droppedCount += 1 })

    XCTAssertEqual(result, .rejectedOwnerChange)
    XCTAssertEqual(droppedCount, 1)
  }

  // MARK: - Persistent card queue policy

  /// A persistent card (meeting summary share) has no timeout, so a newcomer
  /// must displace it — with the persistent card requeued at the front — or a
  /// single un-acted card would starve every later proactive notification.
  func testPersistentCardIsDisplacedByNewcomerExceptDuringAIConversation() {
    XCTAssertTrue(
      FloatingBarNotificationQueuePolicy.shouldDisplacePersistentCard(
        currentIsPersistent: true, showingAIConversation: false))
    XCTAssertFalse(
      FloatingBarNotificationQueuePolicy.shouldDisplacePersistentCard(
        currentIsPersistent: true, showingAIConversation: true))
    XCTAssertFalse(
      FloatingBarNotificationQueuePolicy.shouldDisplacePersistentCard(
        currentIsPersistent: false, showingAIConversation: false))
  }

  @MainActor
  func testNotificationsAreNotPersistentByDefault() {
    let plain = FloatingBarNotification(
      ownerID: "owner", title: "t", message: "m", assistantId: "default", kind: .functional)
    XCTAssertFalse(plain.isPersistent)
    let share = FloatingBarNotification(
      ownerID: "owner", title: "t", message: "m",
      assistantId: MeetingActionItemBannerPolicy.assistantID,
      kind: .meetingNotes,
      action: .meetingSummaryShare(conversationID: "c1", recipients: []),
      isPersistent: true)
    XCTAssertTrue(share.isPersistent)
  }

  @MainActor
  func testSeeSummaryNavigationDrivesConversationOpenContract() {
    final class Captured: @unchecked Sendable {
      var navigatePayload: Int?
      var openRequested = false
    }
    let conversationID = "conv-see-summary-\(UUID().uuidString)"
    let captured = Captured()
    let center = NotificationCenter.default
    let navToken = center.addObserver(
      forName: .navigateToSidebarItem, object: nil, queue: nil
    ) { note in
      captured.navigatePayload = note.userInfo?["rawValue"] as? Int
    }
    let openToken = center.addObserver(
      forName: .desktopAutomationOpenConversationRequested, object: nil, queue: nil
    ) { _ in captured.openRequested = true }
    defer {
      center.removeObserver(navToken)
      center.removeObserver(openToken)
    }

    MeetingSummaryShareActions.postOpenSignals(conversationID: conversationID)

    XCTAssertEqual(captured.navigatePayload, SidebarNavItem.conversations.rawValue)
    XCTAssertTrue(captured.openRequested)
    let pending = ConversationDetailAutomationState.shared.takePendingOpenRequest()
    XCTAssertEqual(pending?.conversationId, conversationID)
    XCTAssertEqual(pending?.showTranscript, false)
  }

  /// Multiple notifications arriving during displacement present before the
  /// persistent card returns: it always rejoins at the tail of the queue.
  func testDisplacedPersistentCardRequeuesBehindEverythingAlreadyQueued() {
    XCTAssertEqual(FloatingBarNotificationQueuePolicy.requeueIndex(queueCount: 0), 0)
    XCTAssertEqual(FloatingBarNotificationQueuePolicy.requeueIndex(queueCount: 3), 3)
  }

  // MARK: - Notch-only proactive cards

  /// The whole point: a card that is actually spoken never grows the bar into the panel.
  func testSpokenCardStaysInTheNotch() {
    XCTAssertTrue(
      FloatingBarNotchOnlyCardPolicy.staysInNotch(
        spokenAloud: true, hasAction: false, isPersistent: false))
  }

  /// A silent card still takes the panel. This is what keeps the change safe to turn on —
  /// suppressing the panel for something nobody hears would deliver it to nobody.
  func testSilentCardStillTakesThePanel() {
    XCTAssertFalse(
      FloatingBarNotchOnlyCardPolicy.staysInNotch(
        spokenAloud: false, hasAction: false, isPersistent: false))
  }

  /// A card carrying buttons has to be reachable; a glow cannot be clicked.
  func testCardWithAnActionAlwaysTakesThePanel() {
    XCTAssertFalse(
      FloatingBarNotchOnlyCardPolicy.staysInNotch(
        spokenAloud: true, hasAction: true, isPersistent: false))
  }

  /// A persistent card is waiting on an explicit decision, so it must stay on screen.
  func testPersistentCardAlwaysTakesThePanel() {
    XCTAssertFalse(
      FloatingBarNotchOnlyCardPolicy.staysInNotch(
        spokenAloud: true, hasAction: false, isPersistent: true))
  }
}
