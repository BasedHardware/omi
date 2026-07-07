import Combine
import Foundation

/// Persistent owner of the Conversations page's search: the typed query,
/// debounced execution, and results.
///
/// Lives in `ViewModelContainer` because the page view is recreated on every
/// tab switch — keeping this state on the page meant a typed search vanished
/// whenever the user navigated away and back. Owning the debounce + request
/// here also lets us cancel superseded in-flight searches instead of letting
/// slow responses race each other out of order.
@MainActor
final class ConversationsSearchModel: ObservableObject {
    /// The text in the search field. Updates immediately as the user types;
    /// execution is debounced internally.
    @Published var query: String = ""
    @Published private(set) var results: [ServerConversation] = []
    @Published private(set) var isSearching = false
    @Published private(set) var searchError: String? = nil

    private var lastSearchedQuery: String? = nil
    private var searchTask: Task<Void, Never>? = nil
    private var cancellables = Set<AnyCancellable>()

    init() {
        $query
            .debounce(for: .milliseconds(250), scheduler: DispatchQueue.main)
            .removeDuplicates()
            .sink { [weak self] value in
                self?.performSearch(query: value)
            }
            .store(in: &cancellables)
    }

    func clear() {
        searchTask?.cancel()
        query = ""
        results = []
        searchError = nil
        isSearching = false
        lastSearchedQuery = nil
    }

    func resetSessionState() {
        clear()
    }

    private func performSearch(query: String) {
        guard !query.isEmpty else {
            searchTask?.cancel()
            results = []
            searchError = nil
            isSearching = false
            lastSearchedQuery = nil
            return
        }
        // The debounce pipeline already drops consecutive duplicates; this
        // guards the clear-and-retype path from re-firing identical requests.
        guard query != lastSearchedQuery else { return }
        lastSearchedQuery = query

        isSearching = true
        searchError = nil
        log("Search: Starting search for '\(query)'")
        AnalyticsManager.shared.searchQueryEntered(query: query)

        searchTask?.cancel()
        searchTask = Task {
            do {
                let result = try await APIClient.shared.searchConversations(
                    query: query,
                    page: 1,
                    perPage: 50,
                    includeDiscarded: false
                )
                guard !Task.isCancelled else { return }
                log("Search: Found \(result.items.count) results")
                results = result.items
                isSearching = false
            } catch {
                guard !Task.isCancelled else { return }
                logError("Search: Failed", error: error)
                searchError = error.localizedDescription
                results = []
                isSearching = false
            }
        }
    }
}
