//
//  DesktopAutomationActivationActions.swift — bridge actions for the first-48h activation surfaces.
//
//  Read/drive seams so a QA bundle can prove the surfaces without the cursor:
//  `daily_summary_snapshot` reports the shared daily-summary store shape-only,
//  `open_chat_prefilled` drives the one prefill-without-send entry
//  (`openMainAppChat(prefilledDraft:)`) so `chat_drafts_snapshot` can show the draft landed unsent,
//  `tap_chat_follow_up_chip` performs the chip's own send so the `followup` question origin is
//  observable end to end, and `seed_memory_review_fixture` / `memory_review_snapshot` /
//  `memory_review_vote` bring up and drive the "Things I learned today" rows. Every one is a
//  second caller of production code, never a second implementation.
//
//  Registered from `DesktopAutomationActionRegistry.registerBuiltins()`.
//

import AppKit
import Foundation
import OmiTheme

extension DesktopAutomationActionRegistry {

  func registerActivationActions() {
    register(
      name: "daily_summary_snapshot",
      summary: "Shape-only state of the shared daily-summary store (has summary, date, stat presence; no text)",
      category: "chat",
      surfaces: ["main_chat"],
      safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "daily_summary_snapshot is disabled on production bundles"]
      }
      // Read only: no refresh here, because a refresh can post the "new summary" notch card.
      let store = ChatDailySummaryCoordinator.shared.store
      guard let latest = store.latest else {
        return [
          "hasSummary": "false",
          "isLoading": store.isLoading ? "true" : "false",
          "lastError": store.lastError ?? "",
        ]
      }
      return [
        "hasSummary": "true",
        // Opaque identity, not content: a harness uses it to drive the recap
        // route (`DailyRecapRouteRef`), whose page re-fetches by id.
        "summaryId": latest.id,
        "date": latest.date ?? "",
        "dateLabel": ChatDailySummaryPresentation.dateLabel(for: latest.date, now: Date()) ?? "",
        "headlineLength": String(latest.headline?.count ?? 0),
        "overviewLength": String(latest.overview?.count ?? 0),
        "hasStats": latest.stats == nil ? "false" : "true",
        "highlightCount": String(latest.highlights?.count ?? 0),
        "actionItemCount": String(latest.actionItems?.count ?? 0),
        // Count only, still no text. It is what makes `MemoryReviewSection.maxRows` observable:
        // the wire can carry more learned memories than the card ever renders, and without this
        // a flow cannot tell a card that bounded its rows from a day that produced only three.
        "memoriesLearnedCount": String(latest.memoriesLearned.count),
        "followUp": ChatDailySummaryPresentation.followUpQuestion(for: latest.date, now: Date()),
      ]
    }

    register(
      name: "open_daily_recap_page",
      summary:
        "Open the dedicated daily-recap page for a summary id through the typed recap route "
        + "(same `ChatFirstShellNavigation.openDailyRecap` the recap rows call)",
      params: ["recordID", "date"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "open_daily_recap_page is disabled on production bundles"]
      }
      let recordID = params["recordID"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !recordID.isEmpty else { return ["error": "missing 'recordID'"] }
      let date = params["date"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let before = ChatFirstShellNavigation.shared.route
      ChatFirstShellNavigation.shared.openDailyRecap(
        DailyRecapRouteRef(recordID: recordID, date: date))
      return [
        "requested": "true",
        "previousRoute": before.stableName,
        "route": ChatFirstShellNavigation.shared.route.stableName,
      ]
    }

    register(
      name: "open_chat_prefilled",
      summary: "Open the main chat with `query` prefilled and focused, NOT sent (the first-real-app card path)",
      params: ["query"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "open_chat_prefilled is disabled on production bundles"]
      }
      guard let query = params["query"]?.trimmingCharacters(in: .whitespacesAndNewlines), !query.isEmpty else {
        return ["error": "missing 'query'"]
      }
      guard let target = AppDelegate.summonWindowTarget() else {
        return ["error": "no window target"]
      }
      target.openMainAppChat(prefilledDraft: query)
      return [
        "requested": "true",
        "pendingDraftLength": String(MainChatNavigationRequestStore.shared.pendingDraft?.count ?? 0),
      ]
    }

    register(
      name: "recent_screen_frames_snapshot",
      summary: "Rows the composer's recent-screen-frames menu will offer (loader output, metadata only)",
      params: ["limit"],
      category: "chat",
      surfaces: ["main_chat"],
      safety: "read_only"
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "recent_screen_frames_snapshot is disabled on production bundles"]
      }
      let limit = Int(params["limit"] ?? "") ?? 12
      let rows = await RewindFrameLoader.shared.attachableRows(limit: limit)
      var detail: [String: String] = [
        "rowCount": String(rows.count),
        "hasRows": rows.isEmpty ? "false" : "true",
      ]
      if let first = rows.first {
        // Provenance only, never frame bytes: a harness asserts the menu's
        // shape, and OCR/window text is not automation's to read.
        detail["firstAppName"] = first.appName
        detail["firstAgeSeconds"] = String(Int(Date().timeIntervalSince(first.timestamp)))
      }
      return detail
    }

    register(
      name: "open_chat_prefilled_with_screen_frame",
      summary:
        "Drive the first-real-app card's handoff end to end: capture (or load) the screen referent, "
        + "stage it, and open the chat with the prompt prefilled and the frame attached (not sent)",
      params: ["prompt"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "open_chat_prefilled_with_screen_frame is disabled on production bundles"]
      }
      let trimmedPrompt = params["prompt"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let prompt = trimmedPrompt.isEmpty ? FirstRealAppCardPolicy.prompt : trimmedPrompt
      // The exact chain the card tap's default closure runs, in the same
      // order: summon the chat with the draft first (the window opens now),
      // take the referent from the summon boundary the summon itself
      // recorded, and fall back to the newest stored non-Omi frame when this
      // tap recorded no boundary. The staged frame lands through
      // `ChatProvider.addAttachments` after the composer is up.
      let tappedAt = Date()
      guard let target = AppDelegate.summonWindowTarget() else {
        return ["error": "no window target"]
      }
      target.openMainAppChat(prefilledDraft: prompt, attachedFrame: nil)
      let boundary = await RewindFrameLoader.shared.awaitSummonBoundary(recordedAfter: tappedAt)
      var frame = boundary
      if frame == nil {
        frame = await RewindFrameLoader.shared.loadLatestAttachableFrame(
          maxAgeSeconds: ScreenContextFallbackPolicy.maxFallbackFrameAgeSeconds
        )
      }
      guard let frame else {
        return [
          "error": "no screen referent available (no summon boundary, no fresh frame)",
          "staged": "false",
        ]
      }
      guard
        let attachment = RecentScreenFrameStaging.attachment(
          appName: frame.appName,
          jpegData: frame.data,
          capturedAt: frame.timestamp
        )
      else {
        return ["error": "frame staging failed", "staged": "false"]
      }
      ChatProvider.mainInstance?.addAttachments([attachment])
      return [
        "staged": "true",
        "frameSource": boundary == nil ? "last_external_frame" : "summon_boundary",
        "frameAppName": frame.appName,
        "frameAgeSeconds": String(Int(Date().timeIntervalSince(frame.timestamp))),
        "attachmentBytes": String(attachment.data?.count ?? 0),
      ]
    }

    register(
      name: "chat_composer_snapshot",
      summary: "Main composer state: draft, staged attachments, placeholder, and query-shell mode",
      params: [],
      category: "chat",
      surfaces: ["main_chat"],
      safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "chat_composer_snapshot is disabled on production bundles"]
      }
      return ChatComposerAutomationSnapshot.detail(
        draft: ChatProvider.mainInstance?.draftText
          ?? ChatDraftStore.shared.text(for: .mainChat(contextID: "omi:default")),
        stagedAttachments: ChatProvider.mainInstance?.pendingAttachments.count ?? 0,
        firstAttachment: ChatProvider.mainInstance?.pendingAttachments.first?.fileName ?? "",
        mode: QueryShellComposerAutomation.mode
      )
    }

    register(
      name: "paste_clipboard_into_chat",
      summary:
        "Run the composer's ⌘V path with a screenshot fixture on the clipboard: pasteboard "
        + "classifier, staging, and provider staging (non-prod paste harness; replaces the clipboard)",
      params: [],
      category: "chat",
      surfaces: ["main_chat"]
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "paste_clipboard_into_chat is disabled on production bundles"]
      }
      // The harness cannot set the system clipboard, so the action stages a
      // representative screenshot copy itself: 2×2 red pixels as TIFF, the
      // exact flavor a ⌘⇧⌃4 capture puts on the board. Clobbering the user's
      // real clipboard is why this stays non-prod.
      let pasteboard = NSPasteboard.general
      pasteboard.clearContents()
      guard
        let rep = NSBitmapImageRep(
          bitmapDataPlanes: nil, pixelsWide: 2, pixelsHigh: 2, bitsPerSample: 8,
          samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
          colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
      else {
        return ["error": "could not build clipboard fixture"]
      }
      rep.size = NSSize(width: 2, height: 2)
      for x in 0..<2 {
        for y in 0..<2 {
          rep.setColor(NSColor.red, atX: x, y: y)
        }
      }
      guard let tiff = rep.tiffRepresentation, pasteboard.setData(tiff, forType: .tiff) else {
        return ["error": "could not write clipboard fixture"]
      }
      // The exact chain the composer's paste handler runs: classifier first
      // (⌘V is a text paste when the board carries readable text), then
      // staging, then the provider's add path. The main chat is summoned
      // first so the composer the paste lands on is mounted, exactly as it
      // is when a person presses ⌘V in it.
      let classifierAccepted = OmiTextEditor.pasteCarriesAttachments(pasteboard)
      guard classifierAccepted else {
        return ["classifierAccepted": "false", "staged": "false"]
      }
      guard let target = AppDelegate.summonWindowTarget() else {
        return ["error": "no window target"]
      }
      target.openMainAppChat(prefilledDraft: "")
      let staged = await PasteboardAttachmentStaging.stageAttachments(from: pasteboard)
      if let main = ChatProvider.mainInstance {
        main.addAttachments(staged)
      }
      return [
        "classifierAccepted": "true",
        "staged": staged.isEmpty ? "false" : "true",
        "stagedCount": String(staged.count),
        "firstAttachmentName": staged.first?.fileName ?? "",
      ]
    }

    register(
      name: "tap_chat_follow_up_chip",
      summary:
        "Tap the follow-up chip under the last main-chat answer (same send as the chip) and report "
        + "the `question_asked` origin it produced",
      params: [],
      category: "chat",
      surfaces: ["main_chat"]
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "tap_chat_follow_up_chip is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      // The chip is a property of the answer, so a missing one is a real finding
      // rather than a harness setup error: report it instead of throwing, and
      // the flow's expectation on `question` fails with the reason attached.
      guard let question = provider.automationLastFollowUpQuestion() else {
        return ["error": "no follow-up chip on the last assistant message", "has_chip": "false"]
      }
      // `origin` is only observable where it is emitted: the property is
      // consumed inside `questionAsked` and gone by the time the send returns.
      // Reading it at the same seam the unit tests use keeps this a report of
      // what production emitted rather than a second guess at it.
      let analytics = AnalyticsManager.shared
      let previousCapture = analytics.questionTelemetryCaptureForTests
      var observedOrigin: String?
      analytics.questionTelemetryCaptureForTests = { event, properties in
        guard event == "question_asked", observedOrigin == nil else { return }
        observedOrigin = properties["origin"] as? String
      }
      defer { analytics.questionTelemetryCaptureForTests = previousCapture }

      let accepted = await FollowUpChipTap.send(question: question, provider: provider) != nil
      return [
        "has_chip": "true",
        "question": question,
        "accepted": accepted ? "true" : "false",
        "question_origin": observedOrigin ?? "",
      ]
    }

    registerMemoryReviewActions()
  }

  // MARK: - Memory review card

  /// Bring up, read, and vote on the "Things I learned today" rows.
  ///
  /// The rows render only from a daily summary's `memories_learned`, and the only producer of that
  /// record is the nightly job — a day of conversations and a model call. So on a hermetic bundle
  /// the card was unreachable, and with it the row state machine, the three mutations, and the
  /// verdict read-back. `seed_memory_review_fixture` creates real memories through the production
  /// `POST /v3/memories` and hands their ids to the local-only daily-summary fixture, so the record
  /// arrives through the same `getDailySummaries` read production uses and every ✓ / ✗ addresses a
  /// memory that `/v3/memories/{id}/review` really mutates.
  private func registerMemoryReviewActions() {
    register(
      name: "seed_memory_review_fixture",
      summary:
        "Create `count` real memories and a local-only daily summary that learned them, then "
        + "refresh the shared store so the review card mounts (offline dev stack only)",
      params: ["count", "timeoutMs"],
      category: "chat",
      surfaces: ["main_chat"],
      sideEffects: ["creates memories on the signed-in local account"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "seed_memory_review_fixture is disabled on production bundles"]
      }
      let requested = Int(params["count"] ?? "") ?? MemoryReviewFixture.defaultCount
      guard let wanted = MemoryReviewFixture.rows(count: requested) else {
        return ["error": "count must be 1...\(MemoryReviewFixture.catalog.count)"]
      }

      var seeded: [MemoryReviewFixture.WireMemory] = []
      for row in wanted {
        do {
          let created = try await APIClient.shared.createMemory(
            content: row.content, category: row.category)
          seeded.append(
            .init(memoryID: created.id, content: row.content, category: row.category.rawValue))
        } catch {
          // Named stage, so a flow failure says which half of the fixture broke rather than
          // leaving an empty card to be read as "the card is broken".
          return [
            "error": "createMemory failed: \(MemoryReviewFixture.reason(error))",
            "createdCount": String(seeded.count),
          ]
        }
      }

      let response: MemoryReviewFixture.SeedResponse
      do {
        response = try await APIClient.shared.post(
          MemoryReviewFixture.seedEndpoint,
          body: MemoryReviewFixture.SeedRequest(memories: seeded))
      } catch {
        return [
          "error": "daily-summary fixture seed failed: \(MemoryReviewFixture.reason(error))",
          "createdCount": String(seeded.count),
        ]
      }

      // The store's own refresh, not the coordinator's: `ChatDailySummaryCoordinator.refresh()`
      // also announces a new summary as a notch card, and a harness must not fire the one
      // user-visible notification this surface owns.
      await ChatDailySummaryCoordinator.shared.store.refresh()

      let timeoutMs = Int(params["timeoutMs"] ?? "") ?? 8000
      let mountedRows = await MemoryReviewFixture.waitForMountedRows(
        seeded: Set(seeded.map(\.memoryID)), timeoutMs: timeoutMs)
      return [
        "createdCount": String(seeded.count),
        "summaryId": response.summaryID,
        "memoriesLearned": String(response.memoriesLearned),
        "mountedRows": String(mountedRows),
      ]
    }

    register(
      name: "memory_review_snapshot",
      summary: "Rows the mounted 'Things I learned today' section bound, and the first two verdicts",
      params: [],
      category: "chat",
      surfaces: ["main_chat"],
      safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "memory_review_snapshot is disabled on production bundles"]
      }
      guard let store = MemoryReviewCardRegistry.mounted else {
        return ["error": "no memory review section is mounted", "mounted": "false"]
      }
      var detail: [String: String] = [
        "mounted": "true",
        "source": store.source.rawValue,
        "rowCount": String(store.items.count),
        "maxRows": String(MemoryReviewSection.maxRows),
      ]
      for (index, item) in store.items.prefix(2).enumerated() {
        detail.merge(MemoryReviewFixture.rowDetail(index: index, item: item, store: store)) { current, _ in current }
      }
      return detail
    }

    register(
      name: "memory_review_vote",
      summary:
        "Vote on one mounted review row through the store the ✓ / ✗ buttons call, then report the "
        + "row once the mutation settles",
      params: ["row", "verdict", "timeoutMs"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "memory_review_vote is disabled on production bundles"]
      }
      guard let store = MemoryReviewCardRegistry.mounted else {
        return ["error": "no memory review section is mounted", "mounted": "false"]
      }
      let index = Int(params["row"] ?? "") ?? 0
      guard store.items.indices.contains(index) else {
        return ["error": "row \(index) is outside the \(store.items.count) mounted rows"]
      }
      let raw = (params["verdict"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard let event = MemoryReviewFixture.event(for: raw) else {
        return ["error": "verdict must be 'accept' or 'reject'"]
      }

      let item = store.items[index]
      // The exact call the row's button makes (`MemoryReviewRowView.controls` → `send(.accept)` →
      // the section's closure). Nothing about the transition is re-decided here.
      store.send(event, to: item)
      let timeoutMs = Int(params["timeoutMs"] ?? "") ?? 15000
      let settled = await MemoryReviewFixture.waitForSettled(store: store, item: item, timeoutMs: timeoutMs)

      var detail = MemoryReviewFixture.rowDetail(index: index, item: item, store: store)
      detail["settledInTime"] = settled ? "true" : "false"
      return detail
    }
  }

}
