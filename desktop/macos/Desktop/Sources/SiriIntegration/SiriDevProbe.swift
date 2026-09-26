#if DEBUG
  import AppIntents
  import CoreSpotlight
  import Foundation

  /// Opt-in, synthetic-only runtime proof for the named development bundle.
  /// The probe never reads an account or calls the backend.
  @available(macOS 27, *)
  @MainActor
  enum SiriDevProbe {
    static func run() async {
      guard Bundle.main.bundleIdentifier == "com.omi.omi-siri-intents" else {
        log("SiriDevProbe: refused non-probe bundle")
        return
      }

      let token = "OmiSiriProbe\(UUID().uuidString.replacingOccurrences(of: "-", with: ""))"
      let index = CSSearchableIndex(name: "omi.siri.synthetic.\(UUID().uuidString)")
      let record = MemoryRecord(backendId: token, content: token)
      do {
        try await index.indexAppEntities([MemoryEntity(record)], priority: 0)
        log("SiriDevProbe: synthetic MemoryEntity indexed")
        let found = await spotlightContains(token)
        log("SiriDevProbe: Core Spotlight fetch found=\(found)")
      } catch {
        log("SiriDevProbe: Core Spotlight index failed: \(error.localizedDescription)")
      }
      do {
        try await index.deleteAllSearchableItems()
        log("SiriDevProbe: synthetic index wiped")
      } catch {
        log("SiriDevProbe: synthetic index wipe failed: \(error.localizedDescription)")
      }

      let observer = NotificationCenter.default.addObserver(
        forName: .navigateToTasks, object: nil, queue: nil
      ) { _ in log("SiriDevProbe: Open list navigation notification observed") }
      let open = OmiOpenListIntent()
      open.target = .omi
      var donation: IntentDonationIdentifier?
      do {
        donation = try await IntentDonationManager.shared.donate(intent: open)
        log("SiriDevProbe: synthetic Open list intent donated")
      } catch {
        log("SiriDevProbe: synthetic donation failed: \(error.localizedDescription)")
      }
      do {
        _ = try await open.perform()
        log("SiriDevProbe: Open list intent performed")
      } catch {
        log("SiriDevProbe: Open list intent failed: \(error.localizedDescription)")
      }
      NotificationCenter.default.removeObserver(observer)
      if let donation {
        do {
          try await IntentDonationManager.shared.deleteDonations(matching: .donationIdentifier(donation))
          log("SiriDevProbe: synthetic donation deleted")
        } catch {
          log("SiriDevProbe: synthetic donation cleanup failed: \(error.localizedDescription)")
        }
      }
    }

    private static func spotlightContains(_ token: String) async -> Bool {
      let context = CSSearchQueryContext()
      context.fetchAttributes = ["contentDescription", "uniqueIdentifier"]
      let query = CSSearchQuery(queryString: "contentDescription == \"\(token)\"", queryContext: context)
      let search = Task { () -> Bool in
        do {
          for try await hit in query.results {
            if hit.item.attributeSet.contentDescription == token { return true }
          }
        } catch { log("SiriDevProbe: Core Spotlight query failed: \(error.localizedDescription)") }
        return false
      }
      let timeout = Task {
        try? await Task.sleep(for: .seconds(10))
        search.cancel()
      }
      let found = await search.value
      timeout.cancel()
      return found
    }
  }
#endif
