import SwiftUI
import Combine

// MARK: - Task Category (by due date)

enum TaskCategory: String, CaseIterable {
    case today = "Today"
    case tomorrow = "Tomorrow"
    case later = "Later"
    case noDeadline = "No Deadline"

    var icon: String {
        switch self {
        case .today: return "sun.max.fill"
        case .tomorrow: return "sunrise.fill"
        case .later: return "calendar"
        case .noDeadline: return "tray.fill"
        }
    }

    var color: Color {
        switch self {
        case .today: return OmiColors.textPrimary
        case .tomorrow: return OmiColors.textSecondary
        case .later: return OmiColors.textSecondary
        case .noDeadline: return OmiColors.textTertiary
        }
    }
}

// MARK: - Task Filter Tag

enum TaskFilterGroup: String, CaseIterable {
    case status = "Status"
    case date = "Date Range"
    case category = "Category"
    case source = "Source"
    case priority = "Priority"
    case origin = "Origin"
}

enum TaskFilterTag: String, CaseIterable, Identifiable, Hashable {
    // Status
    case todo
    case done
    case removedByAI
    case removedByMe

    // Category (matches TaskClassification)
    case personal
    case work
    case feature
    case bug
    case code
    case research
    case communication
    case finance
    case health
    case other

    // Source
    case sourceScreen
    case sourceOmi
    case sourceDesktop
    case sourceManual
    case sourceOmiAnalytics

    // Priority
    case priorityHigh
    case priorityMedium
    case priorityLow

    // Date Range
    case last7Days

    // Origin (source classification)
    case originDirectRequest
    case originSelfGenerated
    case originCalendarDriven
    case originReactive
    case originExternalSystem
    case originOther

    var id: String { rawValue }

    var group: TaskFilterGroup {
        switch self {
        case .todo, .done, .removedByAI, .removedByMe: return .status
        case .last7Days: return .date
        case .personal, .work, .feature, .bug, .code, .research, .communication, .finance, .health, .other: return .category
        case .sourceScreen, .sourceOmi, .sourceDesktop, .sourceManual, .sourceOmiAnalytics: return .source
        case .priorityHigh, .priorityMedium, .priorityLow: return .priority
        case .originDirectRequest, .originSelfGenerated, .originCalendarDriven, .originReactive, .originExternalSystem, .originOther: return .origin
        }
    }

    var displayName: String {
        switch self {
        case .todo: return "To Do"
        case .done: return "Done"
        case .removedByAI: return "Removed by AI"
        case .removedByMe: return "Removed by me"
        case .last7Days: return "Last 7 days"
        case .personal: return "Personal"
        case .work: return "Work"
        case .feature: return "Feature"
        case .bug: return "Bug"
        case .code: return "Code"
        case .research: return "Research"
        case .communication: return "Communication"
        case .finance: return "Finance"
        case .health: return "Health"
        case .other: return "Other"
        case .sourceScreen: return "Screen"
        case .sourceOmi: return "OMI"
        case .sourceDesktop: return "Desktop"
        case .sourceManual: return "Manual"
        case .sourceOmiAnalytics: return "OMI Analytics"
        case .priorityHigh: return "High"
        case .priorityMedium: return "Medium"
        case .priorityLow: return "Low"
        case .originDirectRequest: return "Direct Request"
        case .originSelfGenerated: return "Self-Generated"
        case .originCalendarDriven: return "Calendar-Driven"
        case .originReactive: return "Reactive"
        case .originExternalSystem: return "External System"
        case .originOther: return "Other Origin"
        }
    }

    var icon: String {
        switch self {
        case .todo: return "circle"
        case .done: return "checkmark.circle.fill"
        case .removedByAI: return "trash.slash"
        case .removedByMe: return "trash"
        case .last7Days: return "clock.arrow.circlepath"
        case .personal: return "person.fill"
        case .work: return "briefcase.fill"
        case .feature: return "sparkles"
        case .bug: return "ladybug.fill"
        case .code: return "chevron.left.forwardslash.chevron.right"
        case .research: return "magnifyingglass"
        case .communication: return "message.fill"
        case .finance: return "dollarsign.circle.fill"
        case .health: return "heart.fill"
        case .other: return "folder.fill"
        case .sourceScreen: return "camera.fill"
        case .sourceOmi: return "waveform"
        case .sourceDesktop: return "desktopcomputer"
        case .sourceManual: return "square.and.pencil"
        case .sourceOmiAnalytics: return "chart.bar.fill"
        case .priorityHigh: return "flag.fill"
        case .priorityMedium: return "flag"
        case .priorityLow: return "flag"
        case .originDirectRequest: return "bubble.left.fill"
        case .originSelfGenerated: return "lightbulb.fill"
        case .originCalendarDriven: return "calendar"
        case .originReactive: return "exclamationmark.triangle.fill"
        case .originExternalSystem: return "server.rack"
        case .originOther: return "questionmark.circle"
        }
    }

    /// Check if a task matches this filter tag
    func matches(_ task: TaskActionItem) -> Bool {
        switch self {
        case .todo: return !task.completed
        case .done: return task.completed
        case .removedByAI: return task.deleted == true && task.deletedBy != "user"
        case .removedByMe: return task.deleted == true && task.deletedBy == "user"
        case .last7Days:
            let sevenDaysAgo = Calendar.current.date(byAdding: .day, value: -7, to: Date())!
            if let dueAt = task.dueAt {
                return dueAt >= sevenDaysAgo
            } else {
                return task.createdAt >= sevenDaysAgo
            }
        case .personal: return task.tags.contains("personal")
        case .work: return task.tags.contains("work")
        case .feature: return task.tags.contains("feature")
        case .bug: return task.tags.contains("bug")
        case .code: return task.tags.contains("code")
        case .research: return task.tags.contains("research")
        case .communication: return task.tags.contains("communication")
        case .finance: return task.tags.contains("finance")
        case .health: return task.tags.contains("health")
        case .other: return task.tags.contains("other")
        case .sourceScreen: return task.source == "screenshot"
        case .sourceOmi: return task.source == "transcription:omi"
        case .sourceDesktop: return task.source == "transcription:desktop"
        case .sourceManual: return task.source == "manual"
        case .sourceOmiAnalytics: return task.source == "omi-analytics"
        case .priorityHigh: return task.priority == "high"
        case .priorityMedium: return task.priority == "medium"
        case .priorityLow: return task.priority == "low"
        case .originDirectRequest: return task.sourceClassification?.category == .direct_request
        case .originSelfGenerated: return task.sourceClassification?.category == .self_generated
        case .originCalendarDriven: return task.sourceClassification?.category == .calendar_driven
        case .originReactive: return task.sourceClassification?.category == .reactive
        case .originExternalSystem: return task.sourceClassification?.category == .external_system
        case .originOther: return task.sourceClassification?.category == .other
        }
    }

    /// Pre-computed context for efficient batch filtering (avoids per-task Calendar calls)
    struct FilterContext {
        let sevenDaysAgo: Date

        init() {
            self.sevenDaysAgo = Calendar.current.date(byAdding: .day, value: -7, to: Date())!
        }
    }

    /// Efficient match using pre-computed context — use this in batch filter loops
    func matches(_ task: TaskActionItem, context: FilterContext) -> Bool {
        switch self {
        case .last7Days:
            if let dueAt = task.dueAt {
                return dueAt >= context.sevenDaysAgo
            } else {
                return task.createdAt >= context.sevenDaysAgo
            }
        default:
            return matches(task)
        }
    }

    /// Tags grouped by their filter group
    static func tags(for group: TaskFilterGroup) -> [TaskFilterTag] {
        allCases.filter { $0.group == group }
    }

    /// Get the raw source value this tag matches
    var sourceValue: String? {
        switch self {
        case .sourceScreen: return "screenshot"
        case .sourceOmi: return "transcription:omi"
        case .sourceDesktop: return "transcription:desktop"
        case .sourceManual: return "manual"
        case .sourceOmiAnalytics: return "omi-analytics"
        default: return nil
        }
    }

    /// Get the raw category value this tag matches
    var categoryValue: String? {
        switch self {
        case .personal: return "personal"
        case .work: return "work"
        case .feature: return "feature"
        case .bug: return "bug"
        case .code: return "code"
        case .research: return "research"
        case .communication: return "communication"
        case .finance: return "finance"
        case .health: return "health"
        case .other: return "other"
        default: return nil
        }
    }

    /// Get the raw origin category value this tag matches
    var originCategoryValue: String? {
        switch self {
        case .originDirectRequest: return "direct_request"
        case .originSelfGenerated: return "self_generated"
        case .originCalendarDriven: return "calendar_driven"
        case .originReactive: return "reactive"
        case .originExternalSystem: return "external_system"
        case .originOther: return "other"
        default: return nil
        }
    }

    /// All known source values
    static var knownSources: Set<String> {
        Set(allCases.compactMap { $0.sourceValue })
    }

    /// All known category values
    static var knownCategories: Set<String> {
        Set(allCases.compactMap { $0.categoryValue })
    }
}

// MARK: - Dynamic Filter Tag (for unknown sources/categories)

/// Represents a filter tag that was discovered dynamically from task data
struct DynamicFilterTag: Identifiable, Hashable {
    let id: String
    let group: TaskFilterGroup
    let rawValue: String  // The actual value in the task (e.g., "email:inbound")
    let displayName: String
    let icon: String

    /// Create a dynamic tag for an unknown source
    static func source(_ value: String) -> DynamicFilterTag {
        DynamicFilterTag(
            id: "source:\(value)",
            group: .source,
            rawValue: value,
            displayName: formatDisplayName(value),
            icon: "arrow.right.circle"  // Generic source icon
        )
    }

    /// Create a dynamic tag for an unknown category
    static func category(_ value: String) -> DynamicFilterTag {
        DynamicFilterTag(
            id: "category:\(value)",
            group: .category,
            rawValue: value,
            displayName: formatDisplayName(value),
            icon: "tag"  // Generic category icon
        )
    }

    /// Check if a task matches this dynamic tag
    func matches(_ task: TaskActionItem) -> Bool {
        switch group {
        case .source:
            return task.source == rawValue
        case .category:
            return task.tags.contains(rawValue)
        default:
            return false
        }
    }

    /// Format a raw value into a display name
    /// e.g., "omi-analytics" -> "Omi Analytics", "email:inbound" -> "Email Inbound"
    private static func formatDisplayName(_ value: String) -> String {
        value
            .replacingOccurrences(of: ":", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .replacingOccurrences(of: "_", with: " ")
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst().lowercased() }
            .joined(separator: " ")
    }
}

// MARK: - Saved Filter View

struct SavedFilterView: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let predefinedTagRawValues: [String]
    let dynamicTagIds: [String]  // stored as "group:rawValue" e.g. "source:email:inbound"

    init(name: String, predefinedTags: Set<TaskFilterTag>, dynamicTags: Set<DynamicFilterTag>) {
        self.id = UUID().uuidString
        self.name = name
        self.predefinedTagRawValues = predefinedTags.map { $0.rawValue }
        self.dynamicTagIds = dynamicTags.map { $0.id }
    }

    func restoredPredefinedTags() -> Set<TaskFilterTag> {
        Set(predefinedTagRawValues.compactMap { TaskFilterTag(rawValue: $0) })
    }

    func restoredDynamicTags(from available: [DynamicFilterTag]) -> Set<DynamicFilterTag> {
        let idSet = Set(dynamicTagIds)
        return Set(available.filter { idSet.contains($0.id) })
    }
}

// MARK: - Unified Filter Tag (wraps both predefined and dynamic)

enum UnifiedFilterTag: Identifiable, Hashable {
    case predefined(TaskFilterTag)
    case dynamic(DynamicFilterTag)

    var id: String {
        switch self {
        case .predefined(let tag): return "predefined:\(tag.rawValue)"
        case .dynamic(let tag): return tag.id
        }
    }

    var group: TaskFilterGroup {
        switch self {
        case .predefined(let tag): return tag.group
        case .dynamic(let tag): return tag.group
        }
    }

    var displayName: String {
        switch self {
        case .predefined(let tag): return tag.displayName
        case .dynamic(let tag): return tag.displayName
        }
    }

    var icon: String {
        switch self {
        case .predefined(let tag): return tag.icon
        case .dynamic(let tag): return tag.icon
        }
    }

    func matches(_ task: TaskActionItem) -> Bool {
        switch self {
        case .predefined(let tag): return tag.matches(task)
        case .dynamic(let tag): return tag.matches(task)
        }
    }

    /// Get the raw source value if this is a source filter
    var sourceValue: String? {
        switch self {
        case .predefined(let tag): return tag.sourceValue
        case .dynamic(let tag): return tag.group == .source ? tag.rawValue : nil
        }
    }

    /// Get the raw category value if this is a category filter
    var categoryValue: String? {
        switch self {
        case .predefined(let tag): return tag.categoryValue
        case .dynamic(let tag): return tag.group == .category ? tag.rawValue : nil
        }
    }

    /// Get the raw origin category value if this is an origin filter
    var originCategoryValue: String? {
        switch self {
        case .predefined(let tag): return tag.originCategoryValue
        case .dynamic(_): return nil
        }
    }
}

// MARK: - Tasks View Model (uses shared TasksStore)

@MainActor
class TasksViewModel: ObservableObject {
    // Use shared TasksStore as single source of truth
    private let store = TasksStore.shared

    // Search state - searches SQLite directly
    @Published var searchText = "" {
        didSet {
            if oldValue != searchText {
                displayLimit = 100
                keyboardSelectedTaskId = nil
                isInlineCreating = false
                Task { await performSearch() }
            }
        }
    }
    @Published private(set) var isSearching = false
    @Published private(set) var searchResults: [TaskActionItem] = []

    // UI-specific state
    @Published var showCompleted = false {
        didSet {
            if oldValue != showCompleted {
                // Load appropriate tasks from server when switching tabs
                Task {
                    if showCompleted {
                        await store.loadCompletedTasks()
                    } else {
                        await store.loadIncompleteTasks()
                    }
                }
            }
            recomputeDisplayCaches()
        }
    }
    // Filter tags (Memories-style dropdown)
    @Published var selectedTags: Set<TaskFilterTag> = [.todo, .last7Days] {
        didSet {
            // Reset display limit and keyboard selection when filters change
            displayLimit = 100
            keyboardSelectedTaskId = nil
            isInlineCreating = false

            // Map status tags to showCompleted for server-side loading
            let hasStatusFilter = selectedTags.contains(where: { $0.group == .status })
            if hasStatusFilter {
                let wantsDone = selectedTags.contains(.done)
                let wantsTodo = selectedTags.contains(.todo)
                let wantsDeleted = selectedTags.contains(.removedByAI) || selectedTags.contains(.removedByMe)
                if wantsDeleted {
                    // Load deleted tasks from server
                    Task { await store.loadDeletedTasks() }
                }
                if wantsDone && !wantsTodo && !wantsDeleted && !showCompleted {
                    showCompleted = true
                } else if wantsTodo && !wantsDone && !wantsDeleted && showCompleted {
                    showCompleted = false
                } else if wantsDone && wantsTodo {
                    // Both selected - load both
                    if !showCompleted {
                        Task { await store.loadCompletedTasks() }
                    }
                }
            }
            // When non-status filters (including date) are applied, query SQLite directly
            let hasNonStatusFilters = selectedTags.contains(where: { $0.group != .status })
            if hasNonStatusFilters {
                Task { await loadFilteredTasksFromDatabase() }
            } else {
                filteredFromDatabase = []
                recomputeDisplayCaches()
            }
        }
    }

    /// Tasks loaded from SQLite with filters applied
    @Published private(set) var filteredFromDatabase: [TaskActionItem] = []
    @Published private(set) var isLoadingFiltered = false

    /// Cached tag counts - recomputed when tasks change (not @Published to avoid extra re-renders;
    /// values are read during re-renders triggered by displayTasks/categorizedTasks changes)
    private(set) var tagCounts: [TaskFilterTag: Int] = [:]

    /// Dynamically discovered tags (sources/categories not in predefined list)
    private(set) var dynamicTags: [DynamicFilterTag] = []

    /// Counts for dynamic tags
    private(set) var dynamicTagCounts: [String: Int] = [:]

    /// Selected dynamic tags
    @Published var selectedDynamicTags: Set<DynamicFilterTag> = [] {
        didSet {
            displayLimit = 100
            keyboardSelectedTaskId = nil
            isInlineCreating = false
            if !selectedDynamicTags.isEmpty {
                Task { await loadFilteredTasksFromDatabase() }
            } else if selectedTags.isEmpty || !selectedTags.contains(where: { $0.group != .status }) {
                filteredFromDatabase = []
                recomputeDisplayCaches()
            }
        }
    }

    /// Count tasks for a specific tag
    func tagCount(_ tag: TaskFilterTag) -> Int {
        tagCounts[tag] ?? 0
    }

    /// Count tasks for a dynamic tag
    func dynamicTagCount(_ tag: DynamicFilterTag) -> Int {
        dynamicTagCounts[tag.id] ?? 0
    }

    /// Get all available tags for a group (predefined + dynamic)
    func availableTags(for group: TaskFilterGroup) -> [UnifiedFilterTag] {
        var tags: [UnifiedFilterTag] = []

        // Add predefined tags
        for tag in TaskFilterTag.tags(for: group) {
            tags.append(.predefined(tag))
        }

        // Add dynamic tags for this group
        for tag in dynamicTags where tag.group == group {
            tags.append(.dynamic(tag))
        }

        return tags
    }

    /// Check if any filters are active (predefined or dynamic)
    var hasActiveFilters: Bool {
        !selectedTags.isEmpty || !selectedDynamicTags.isEmpty
    }

    /// Clear all filters
    func clearAllFilters() {
        selectedTags.removeAll()
        selectedDynamicTags.removeAll()
    }

    // MARK: - Saved Filter Views

    private static let savedFilterViewsKey = "TasksSavedFilterViews"
    @Published var savedFilterViews: [SavedFilterView] = []

    /// Whether current filters differ from the default [.todo, .last7Days]
    var hasNonDefaultFilters: Bool {
        let isDefault = selectedTags == [.todo, .last7Days] && selectedDynamicTags.isEmpty
        let isEmpty = selectedTags.isEmpty && selectedDynamicTags.isEmpty
        return !isDefault && !isEmpty
    }

    func saveCurrentFilters(name: String) {
        let view = SavedFilterView(name: name, predefinedTags: selectedTags, dynamicTags: selectedDynamicTags)
        savedFilterViews.append(view)
        persistSavedFilterViews()
    }

    func applySavedView(_ view: SavedFilterView) {
        selectedTags = view.restoredPredefinedTags()
        selectedDynamicTags = view.restoredDynamicTags(from: dynamicTags)
    }

    func deleteSavedView(_ view: SavedFilterView) {
        savedFilterViews.removeAll { $0.id == view.id }
        persistSavedFilterViews()
    }

    func isActiveSavedView(_ view: SavedFilterView) -> Bool {
        let predefined = view.restoredPredefinedTags()
        let dynamic = view.restoredDynamicTags(from: dynamicTags)
        return selectedTags == predefined && selectedDynamicTags == dynamic
    }

    private func loadSavedFilterViews() {
        guard let data = UserDefaults.standard.data(forKey: Self.savedFilterViewsKey),
              let views = try? JSONDecoder().decode([SavedFilterView].self, from: data) else {
            return
        }
        savedFilterViews = views
    }

    private func persistSavedFilterViews() {
        guard let data = try? JSONEncoder().encode(savedFilterViews) else { return }
        UserDefaults.standard.set(data, forKey: Self.savedFilterViewsKey)
    }

    // Keyboard navigation state
    @Published var keyboardSelectedTaskId: String?
    @Published var isInlineCreating = false
    @Published var inlineCreateAfterTaskId: String?
    @Published var editingTaskId: String?
    var hoveredTaskId: String?
    @Published var animateToggleTaskId: String?
    @Published var isAnyTaskEditing = false
    var lastEnterPressTime: Date?
    var scrollProxy: ScrollViewProxy?

    /// Flat task list matching visual order (for arrow key navigation)
    var navigationOrder: [TaskActionItem] {
        let onlyDone = selectedTags.contains(.done) && !selectedTags.contains(.todo)
        let onlyDeleted = (selectedTags.contains(.removedByAI) || selectedTags.contains(.removedByMe)) && !selectedTags.contains(.todo) && !selectedTags.contains(.done)
        if !onlyDone && !onlyDeleted && !isMultiSelectMode {
            return TaskCategory.allCases.flatMap { getOrderedTasks(for: $0) }
        } else {
            return displayTasks
        }
    }

    // Create/Edit task state
    @Published var showingCreateTask = false

    // Undo stack for deleted tasks
    struct UndoableAction {
        let task: TaskActionItem
        let timestamp: Date
    }
    @Published var undoStack: [UndoableAction] = []  // max 10
    @Published var showUndoToast = false
    var undoToastDismissTask: Task<Void, Never>?

    // Multi-select state
    @Published var isMultiSelectMode = false
    @Published var selectedTaskIds: Set<String> = []

    // MARK: - Drag-and-Drop Reordering (like Flutter)
    /// Custom order of task IDs per category (persisted to UserDefaults as fallback)
    @Published var categoryOrder: [TaskCategory: [String]] = [:] {
        didSet { saveCategoryOrder() }
    }

    // MARK: - Task Indentation (like Flutter)
    /// Indent levels for tasks (0-3), persisted to UserDefaults as fallback
    @Published var indentLevels: [String: Int] = [:] {
        didSet { saveIndentLevels() }
    }

    /// Debounced task for syncing sort orders to SQLite + backend
    private var sortOrderSyncTask: Task<Void, Never>?

    private var cancellables = Set<AnyCancellable>()

    /// Version counter to coalesce rapid recomputation requests
    private var recomputeVersion: Int = 0

    /// Throttle flag for loadMoreIfNeeded to prevent task storms during fast scroll
    private var isLoadingMoreGuard = false

    /// Minimum interval between pagination triggers (seconds)
    private var lastLoadMoreTime: Date = .distantPast
    private let loadMoreThrottleInterval: TimeInterval = 0.5

    // MARK: - Cached Properties (avoid recomputation on every render)

    @Published private(set) var displayTasks: [TaskActionItem] = []
    @Published private(set) var categorizedTasks: [TaskCategory: [TaskActionItem]] = [:]
    private(set) var todoCount: Int = 0
    private(set) var doneCount: Int = 0

    /// Whether there are more filtered/search results beyond the display limit
    private(set) var hasMoreFilteredResults = false

    /// Full filtered results before display cap (kept for pagination)
    private var allFilteredDisplayTasks: [TaskActionItem] = []

    /// Current display limit for filtered/search results
    private var displayLimit = 100

    // Delegate to store
    var isLoading: Bool { store.isLoading }
    var isLoadingMore: Bool { store.isLoadingMore }
    var hasMoreTasks: Bool {
        showCompleted ? store.hasMoreCompletedTasks : store.hasMoreIncompleteTasks
    }
    var error: String? { store.error }
    var tasks: [TaskActionItem] { store.tasks }

    init() {
        // Load saved order, indent levels, and saved filter views
        loadCategoryOrder()
        loadIndentLevels()
        loadSavedFilterViews()

        // Forward store changes to trigger view updates and recompute caches
        // Debounced so surgical single-item updates don't cause a redundant full recompute
        store.objectWillChange
            .receive(on: DispatchQueue.main)
            .debounce(for: .milliseconds(300), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.recomputeAllCaches()
            }
            .store(in: &cancellables)

        // Migrate UserDefaults ordering to sortOrder fields
        migrateUserDefaultsToSortOrder()
    }

    // MARK: - Persistence (UserDefaults)

    private static let categoryOrderKey = "TasksCategoryOrder"
    private static let indentLevelsKey = "TasksIndentLevels"

    private func loadCategoryOrder() {
        guard let data = UserDefaults.standard.dictionary(forKey: Self.categoryOrderKey) as? [String: [String]] else {
            return
        }
        var order: [TaskCategory: [String]] = [:]
        for (key, ids) in data {
            if let category = TaskCategory(rawValue: key) {
                order[category] = ids
            }
        }
        categoryOrder = order
    }

    private func saveCategoryOrder() {
        var data: [String: [String]] = [:]
        for (category, ids) in categoryOrder {
            data[category.rawValue] = ids
        }
        UserDefaults.standard.set(data, forKey: Self.categoryOrderKey)
    }

    private func loadIndentLevels() {
        guard let data = UserDefaults.standard.dictionary(forKey: Self.indentLevelsKey) as? [String: Int] else {
            return
        }
        indentLevels = data
    }

    private func saveIndentLevels() {
        UserDefaults.standard.set(indentLevels, forKey: Self.indentLevelsKey)
    }

    // MARK: - Drag-and-Drop Methods

    /// Get ordered tasks for a category, matching Python backend sort: due_at ASC, created_at DESC
    func getOrderedTasks(for category: TaskCategory) -> [TaskActionItem] {
        guard let tasks = categorizedTasks[category], !tasks.isEmpty else {
            return []
        }

        // Fall back to legacy UserDefaults categoryOrder if present (local drag-and-drop)
        if let order = categoryOrder[category], !order.isEmpty {
            var orderedTasks: [TaskActionItem] = []
            var taskMap = Dictionary(tasks.map { ($0.id, $0) }, uniquingKeysWith: { _, latest in latest })

            for id in order {
                if let task = taskMap[id] {
                    orderedTasks.append(task)
                    taskMap.removeValue(forKey: id)
                }
            }

            // Remaining tasks not in custom order
            let remaining = taskMap.values.sorted { a, b in
                let aDue = a.dueAt ?? .distantFuture
                let bDue = b.dueAt ?? .distantFuture
                if aDue != bDue { return aDue < bDue }
                return a.createdAt > b.createdAt
            }
            orderedTasks.append(contentsOf: remaining)
            return orderedTasks
        }

        // Default sort: due_at ascending (nulls last), created_at descending (newest first)
        return tasks.sorted { a, b in
            let aDue = a.dueAt ?? .distantFuture
            let bDue = b.dueAt ?? .distantFuture
            if aDue != bDue { return aDue < bDue }
            return a.createdAt > b.createdAt
        }
    }

    /// Move a task within a category
    func moveTask(_ task: TaskActionItem, toIndex targetIndex: Int, inCategory category: TaskCategory) {
        var order = categoryOrder[category] ?? categorizedTasks[category]?.map { $0.id } ?? []

        // Remove task from current position
        order.removeAll { $0 == task.id }

        // Insert at new position
        let safeIndex = min(targetIndex, order.count)
        order.insert(task.id, at: safeIndex)

        categoryOrder[category] = order

        // Compute sortOrder values for all tasks in this category and schedule sync
        scheduleSortOrderSync()
    }

    /// Move a task to first position in category
    func moveTaskToFirst(_ task: TaskActionItem, inCategory category: TaskCategory) {
        moveTask(task, toIndex: 0, inCategory: category)
    }

    // MARK: - Indent Methods

    func getIndentLevel(for taskId: String) -> Int {
        // Local in-session overrides take priority, then fall back to persisted value from backend/SQLite
        if let local = indentLevels[taskId] {
            return local
        }
        if let task = store.incompleteTasks.first(where: { $0.id == taskId }) ?? store.completedTasks.first(where: { $0.id == taskId }),
           let level = task.indentLevel {
            return level
        }
        return 0
    }

    func incrementIndent(for taskId: String) {
        let current = getIndentLevel(for: taskId)
        if current < 3 {
            indentLevels[taskId] = current + 1
            scheduleSortOrderSync()
        }
    }

    func decrementIndent(for taskId: String) {
        let current = getIndentLevel(for: taskId)
        if current > 0 {
            indentLevels[taskId] = current - 1
            scheduleSortOrderSync()
        }
    }

    // MARK: - Keyboard Navigation

    /// Find a task by ID across all store arrays
    func findTask(_ id: String) -> TaskActionItem? {
        store.incompleteTasks.first(where: { $0.id == id })
            ?? store.completedTasks.first(where: { $0.id == id })
    }

    /// Move keyboard selection up or down
    func moveSelection(_ direction: Int) {
        let nav = navigationOrder
        guard !nav.isEmpty else { return }

        if let currentId = keyboardSelectedTaskId,
           let currentIndex = nav.firstIndex(where: { $0.id == currentId }) {
            let newIndex = min(max(currentIndex + direction, 0), nav.count - 1)
            let newId = nav[newIndex].id
            keyboardSelectedTaskId = newId
            scrollProxy?.scrollTo(newId, anchor: .center)
        } else {
            let task = direction > 0 ? nav.first : nav.last
            if let task = task {
                keyboardSelectedTaskId = task.id
                scrollProxy?.scrollTo(task.id, anchor: .center)
            }
        }
    }

    /// Handle a key-down event. Returns true if the event was consumed.
    func handleKeyDown(_ event: NSEvent) -> Bool {
        // Don't intercept keys when a text field has focus
        if let firstResponder = NSApp.keyWindow?.firstResponder,
           firstResponder is NSTextView || firstResponder is NSTextField {
            return false
        }

        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        let keyCode = event.keyCode

        // Cmd+N: new task
        if modifiers == .command && keyCode == 45 {
            showingCreateTask = true
            return true
        }

        // Cmd+D: delete task
        if modifiers == .command && keyCode == 2 {
            guard let taskId = keyboardSelectedTaskId ?? hoveredTaskId,
                  let task = findTask(taskId) else { return false }
            let nav = navigationOrder
            if let idx = nav.firstIndex(where: { $0.id == taskId }) {
                let nextIdx = idx + 1 < nav.count ? idx + 1 : max(0, idx - 1)
                if nav.count > 1 {
                    keyboardSelectedTaskId = nav[nextIdx].id
                } else {
                    keyboardSelectedTaskId = nil
                }
            }
            Task { [weak self] in await self?.deleteTaskWithUndo(task) }
            return true
        }

        // Space: toggle task complete (triggers animation in TaskRow)
        if keyCode == 49 && modifiers.isEmpty {
            guard let taskId = keyboardSelectedTaskId ?? hoveredTaskId,
                  findTask(taskId) != nil else { return false }
            animateToggleTaskId = taskId
            // Reset so pressing space on the same task again triggers onChange
            DispatchQueue.main.async { [weak self] in
                self?.animateToggleTaskId = nil
            }
            return true
        }

        // Tab / Shift+Tab: indent
        if keyCode == 48 && modifiers.isEmpty {
            guard let taskId = keyboardSelectedTaskId ?? hoveredTaskId else { return false }
            incrementIndent(for: taskId)
            return true
        }
        if keyCode == 48 && modifiers == .shift {
            guard let taskId = keyboardSelectedTaskId ?? hoveredTaskId else { return false }
            decrementIndent(for: taskId)
            return true
        }

        // Guard: don't navigate while editing or inline creating
        guard !isAnyTaskEditing && !isInlineCreating else { return false }

        // Guard: don't navigate in multi-select mode
        guard !isMultiSelectMode else { return false }

        // Arrow Up/Down navigation (arrow keys set .numericPad/.function flags on macOS)
        let userModifiers = modifiers.subtracting([.numericPad, .function])
        if keyCode == 126 && userModifiers.isEmpty { // Up
            moveSelection(-1)
            return true
        }
        if keyCode == 125 && userModifiers.isEmpty { // Down
            moveSelection(1)
            return true
        }

        // Enter: inline create or double-enter for edit
        if keyCode == 36 && modifiers.isEmpty && keyboardSelectedTaskId != nil {
            if !searchText.isEmpty { return false }

            let now = Date()
            if let last = lastEnterPressTime, now.timeIntervalSince(last) < 0.4 {
                lastEnterPressTime = nil
                editingTaskId = keyboardSelectedTaskId
                return true
            }
            lastEnterPressTime = now
            let capturedTime = now
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
                guard self?.lastEnterPressTime == capturedTime else { return }
                self?.lastEnterPressTime = nil
                self?.isInlineCreating = true
                self?.inlineCreateAfterTaskId = self?.keyboardSelectedTaskId
            }
            return true
        }

        // Escape: cancel inline create, or deselect
        if keyCode == 53 {
            if isInlineCreating {
                isInlineCreating = false
                inlineCreateAfterTaskId = nil
                return true
            }
            if keyboardSelectedTaskId != nil {
                keyboardSelectedTaskId = nil
                return true
            }
        }

        return false
    }

    // MARK: - Sort Order Sync

    /// Debounced sync of sort orders to SQLite + backend API (500ms)
    private func scheduleSortOrderSync() {
        sortOrderSyncTask?.cancel()
        sortOrderSyncTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms debounce
            guard !Task.isCancelled else { return }
            await self?.syncSortOrders()
        }
    }

    /// Collect current sort orders from all categories and write to SQLite + backend
    private func syncSortOrders() async {
        var updates: [(id: String, sortOrder: Int, indentLevel: Int)] = []

        for category in TaskCategory.allCases {
            let orderedTasks = getOrderedTasks(for: category)
            // Category offset: today=0, tomorrow=100_000, later=200_000, noDeadline=300_000
            let categoryOffset = (TaskCategory.allCases.firstIndex(of: category) ?? 0) * 100_000

            for (index, task) in orderedTasks.enumerated() {
                guard !task.id.hasPrefix("local_"), !task.id.hasPrefix("staged_") else { continue }
                let sortOrder = categoryOffset + (index + 1) * 1000
                let indent = indentLevels[task.id] ?? task.indentLevel ?? 0
                updates.append((id: task.id, sortOrder: sortOrder, indentLevel: indent))
            }
        }

        guard !updates.isEmpty else { return }

        // Write to SQLite
        let storageUpdates = updates.map { (backendId: $0.id, sortOrder: $0.sortOrder, indentLevel: $0.indentLevel) }
        do {
            try await ActionItemStorage.shared.updateSortOrders(storageUpdates)
        } catch {
            log("TasksVM: Failed to write sort orders to SQLite: \(error)")
        }

        // Sync to backend API
        do {
            try await APIClient.shared.batchUpdateSortOrders(updates)
            log("TasksVM: Synced \(updates.count) sort orders to backend")
        } catch {
            log("TasksVM: Failed to sync sort orders to backend: \(error)")
        }
    }

    // MARK: - UserDefaults-to-SortOrder Migration

    /// One-time migration: read existing UserDefaults ordering and write as sortOrder to SQLite + backend
    private func migrateUserDefaultsToSortOrder() {
        let migrationKey = "TasksSortOrderMigrated"
        guard !UserDefaults.standard.bool(forKey: migrationKey) else { return }

        // Only migrate if there's existing UserDefaults ordering data
        let hasOrder = !categoryOrder.isEmpty
        let hasIndents = !indentLevels.isEmpty
        guard hasOrder || hasIndents else {
            UserDefaults.standard.set(true, forKey: migrationKey)
            return
        }

        Task { [weak self] in
            guard let self else { return }
            await self.syncSortOrders()
            UserDefaults.standard.set(true, forKey: migrationKey)
            log("TasksVM: Migrated UserDefaults ordering to sortOrder")
        }
    }

    // MARK: - Cache Recomputation

    /// Get the source tasks based on current view (completed vs incomplete)
    private func getSourceTasks() -> [TaskActionItem] {
        let statusTags = selectedTags.filter { $0.group == .status }

        // If only deleted filters are selected, show only deleted tasks
        let wantsDeletedOnly = (statusTags.contains(.removedByAI) || statusTags.contains(.removedByMe)) && !statusTags.contains(.todo) && !statusTags.contains(.done)
        if wantsDeletedOnly {
            return store.deletedTasks
        }

        // Build combined list from selected status filters
        var result: [TaskActionItem] = []
        if statusTags.isEmpty || statusTags.contains(.todo) || statusTags.contains(.done) {
            if statusTags.isEmpty || (statusTags.contains(.todo) && statusTags.contains(.done)) {
                result = store.incompleteTasks + store.completedTasks
            } else if statusTags.contains(.done) {
                result = store.completedTasks
            } else {
                result = store.incompleteTasks
            }
        }

        // If any deleted filter is also selected alongside other status tags, include deleted
        if statusTags.contains(.removedByAI) || statusTags.contains(.removedByMe) {
            result += store.deletedTasks
        }

        return result
    }

    /// Apply selected filter tags to tasks (non-status tags)
    private func applyTagFilters(_ tasks: [TaskActionItem], context: TaskFilterTag.FilterContext) -> [TaskActionItem] {
        let nonStatusTags = selectedTags.filter { $0.group != .status }
        guard !nonStatusTags.isEmpty else { return tasks }

        // Group tags by their filter group, then AND between groups, OR within a group
        let tagsByGroup = Dictionary(grouping: nonStatusTags) { $0.group }

        return tasks.filter { task in
            tagsByGroup.allSatisfy { (_, groupTags) in
                groupTags.contains { $0.matches(task, context: context) }
            }
        }
    }

    /// Recompute all caches when tasks change
    private func recomputeAllCaches() {
        log("RENDER: recomputeAllCaches triggered")
        recomputeVersion += 1
        let version = recomputeVersion

        // Snapshot inputs for background computation
        let allTasks = store.incompleteTasks + store.completedTasks
        let knownSources = TaskFilterTag.knownSources
        let knownCategories = TaskFilterTag.knownCategories

        // Discover dynamic tags on a background thread (iterates all tasks)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var newDynamicTags: [DynamicFilterTag] = []
            var newDynamicCounts: [String: Int] = [:]

            var allSources: [String: Int] = [:]
            var allCategories: [String: Int] = [:]

            for task in allTasks {
                if let source = task.source, !source.isEmpty {
                    allSources[source, default: 0] += 1
                }
                for tag in task.tags {
                    allCategories[tag, default: 0] += 1
                }
            }

            for (source, count) in allSources {
                if !knownSources.contains(source) {
                    let tag = DynamicFilterTag.source(source)
                    newDynamicTags.append(tag)
                    newDynamicCounts[tag.id] = count
                }
            }

            for (category, count) in allCategories {
                if !knownCategories.contains(category) {
                    let tag = DynamicFilterTag.category(category)
                    newDynamicTags.append(tag)
                    newDynamicCounts[tag.id] = count
                }
            }

            newDynamicTags.sort { (newDynamicCounts[$0.id] ?? 0) > (newDynamicCounts[$1.id] ?? 0) }

            DispatchQueue.main.async { [weak self] in
                guard let self, self.recomputeVersion == version else { return }
                self.dynamicTags = newDynamicTags
                self.dynamicTagCounts = newDynamicCounts
            }
        }

        // If non-status filters (including date) are active, re-query SQLite to pick up changes
        // (e.g. a task was just toggled completed and should no longer appear).
        // Otherwise just recompute from the in-memory store arrays.
        let hasNonStatusFilters = selectedTags.contains(where: { $0.group != .status })
            || !selectedDynamicTags.isEmpty
        if hasNonStatusFilters {
            Task { [weak self] in
                guard let self, self.recomputeVersion == version else { return }
                await self.loadFilteredTasksFromDatabase()
            }
        } else {
            recomputeDisplayCaches()
        }

        // Load true counts from SQLite asynchronously
        Task { [weak self] in
            guard let self, self.recomputeVersion == version else { return }
            await self.loadTagCountsFromDatabase()
        }
    }

    /// Discover unknown sources/categories from task data and create dynamic tags
    private func discoverDynamicTags() {
        let allTasks = store.incompleteTasks + store.completedTasks
        var newDynamicTags: [DynamicFilterTag] = []
        var newDynamicCounts: [String: Int] = [:]

        // Collect all unique sources and categories
        var allSources: [String: Int] = [:]
        var allCategories: [String: Int] = [:]

        for task in allTasks {
            if let source = task.source, !source.isEmpty {
                allSources[source, default: 0] += 1
            }
            for tag in task.tags {
                allCategories[tag, default: 0] += 1
            }
        }

        // Find sources not in predefined list
        let knownSources = TaskFilterTag.knownSources
        for (source, count) in allSources {
            if !knownSources.contains(source) {
                let tag = DynamicFilterTag.source(source)
                newDynamicTags.append(tag)
                newDynamicCounts[tag.id] = count
            }
        }

        // Find categories not in predefined list
        let knownCategories = TaskFilterTag.knownCategories
        for (category, count) in allCategories {
            if !knownCategories.contains(category) {
                let tag = DynamicFilterTag.category(category)
                newDynamicTags.append(tag)
                newDynamicCounts[tag.id] = count
            }
        }

        // Sort by count descending
        newDynamicTags.sort { (dynamicTagCounts[$0.id] ?? 0) > (dynamicTagCounts[$1.id] ?? 0) }

        dynamicTags = newDynamicTags
        dynamicTagCounts = newDynamicCounts
    }

    /// Load filtered tasks from SQLite when non-status filters are applied
    private func loadFilteredTasksFromDatabase() async {
        let nonStatusTags = selectedTags.filter { $0.group != .status && $0.group != .date }
        let dateTags = selectedTags.filter { $0.group == .date }
        let hasDynamicFilters = !selectedDynamicTags.isEmpty

        guard !nonStatusTags.isEmpty || !dateTags.isEmpty || hasDynamicFilters else {
            filteredFromDatabase = []
            recomputeDisplayCaches()
            return
        }

        isLoadingFiltered = true

        // Extract filter values from predefined tags
        let tagsByGroup = Dictionary(grouping: nonStatusTags) { $0.group }

        // Get categories from predefined tags
        var categories: [String] = tagsByGroup[.category]?.compactMap { tag -> String? in
            switch tag {
            case .personal: return "personal"
            case .work: return "work"
            case .feature: return "feature"
            case .bug: return "bug"
            case .code: return "code"
            case .research: return "research"
            case .communication: return "communication"
            case .finance: return "finance"
            case .health: return "health"
            case .other: return "other"
            default: return nil
            }
        } ?? []

        // Add categories from dynamic tags
        for tag in selectedDynamicTags where tag.group == .category {
            categories.append(tag.rawValue)
        }

        // Get sources from predefined tags
        var sources: [String] = tagsByGroup[.source]?.compactMap { tag -> String? in
            switch tag {
            case .sourceScreen: return "screenshot"
            case .sourceOmi: return "transcription:omi"
            case .sourceDesktop: return "transcription:desktop"
            case .sourceManual: return "manual"
            case .sourceOmiAnalytics: return "omi-analytics"
            default: return nil
            }
        } ?? []

        // Add sources from dynamic tags
        for tag in selectedDynamicTags where tag.group == .source {
            sources.append(tag.rawValue)
        }

        // Get priorities
        let priorities: [String]? = tagsByGroup[.priority]?.compactMap { tag -> String? in
            switch tag {
            case .priorityHigh: return "high"
            case .priorityMedium: return "medium"
            case .priorityLow: return "low"
            default: return nil
            }
        }

        // Get origin categories
        let originCategories: [String]? = tagsByGroup[.origin]?.compactMap { $0.originCategoryValue }

        // Determine completed states from status filters
        let statusTags = selectedTags.filter { $0.group == .status }
        let completedStates: [Bool]?
        if statusTags.isEmpty {
            completedStates = nil  // Show all
        } else {
            var states: [Bool] = []
            if statusTags.contains(.todo) { states.append(false) }
            if statusTags.contains(.done) { states.append(true) }
            completedStates = states.isEmpty ? nil : states
        }

        let includeDeleted = statusTags.contains(.removedByAI) || statusTags.contains(.removedByMe)

        // Extract date filter (last7Days)
        let dateAfter: Date? = dateTags.contains(.last7Days)
            ? Calendar.current.date(byAdding: .day, value: -7, to: Date())
            : nil

        do {
            let results = try await ActionItemStorage.shared.getFilteredActionItems(
                limit: 10000,
                completedStates: completedStates,
                includeDeleted: includeDeleted,
                categories: categories.isEmpty ? nil : categories,
                sources: sources.isEmpty ? nil : sources,
                priorities: priorities,
                originCategories: originCategories,
                dateAfter: dateAfter
            )
            filteredFromDatabase = results
            log("TasksViewModel: Loaded \(results.count) filtered tasks from SQLite")
        } catch {
            logError("TasksViewModel: Failed to load filtered tasks", error: error)
            filteredFromDatabase = []
        }

        isLoadingFiltered = false
        recomputeDisplayCaches()
    }

    /// Load tag counts from SQLite database (shows true totals, not just loaded items)
    private func loadTagCountsFromDatabase() async {
        do {
            let filterCounts = try await ActionItemStorage.shared.getFilterCounts()

            // Update counts on main actor
            todoCount = filterCounts.todo
            doneCount = filterCounts.done

            var counts: [TaskFilterTag: Int] = [:]

            // Status counts
            counts[.todo] = filterCounts.todo
            counts[.done] = filterCounts.done
            counts[.removedByAI] = filterCounts.deletedByAI
            counts[.removedByMe] = filterCounts.deletedByUser

            // Category counts
            counts[.personal] = filterCounts.categories["personal"] ?? 0
            counts[.work] = filterCounts.categories["work"] ?? 0
            counts[.feature] = filterCounts.categories["feature"] ?? 0
            counts[.bug] = filterCounts.categories["bug"] ?? 0
            counts[.code] = filterCounts.categories["code"] ?? 0
            counts[.research] = filterCounts.categories["research"] ?? 0
            counts[.communication] = filterCounts.categories["communication"] ?? 0
            counts[.finance] = filterCounts.categories["finance"] ?? 0
            counts[.health] = filterCounts.categories["health"] ?? 0
            counts[.other] = filterCounts.categories["other"] ?? 0

            // Date range counts (computed in-memory)
            let allTasks = store.incompleteTasks + store.completedTasks
            let sevenDaysAgo = Calendar.current.date(byAdding: .day, value: -7, to: Date())!
            counts[.last7Days] = allTasks.filter { task in
                if let dueAt = task.dueAt {
                    return dueAt >= sevenDaysAgo
                } else {
                    return task.createdAt >= sevenDaysAgo
                }
            }.count

            // Source counts
            counts[.sourceScreen] = filterCounts.sources["screenshot"] ?? 0
            counts[.sourceOmi] = filterCounts.sources["transcription:omi"] ?? 0
            counts[.sourceDesktop] = filterCounts.sources["transcription:desktop"] ?? 0
            counts[.sourceManual] = filterCounts.sources["manual"] ?? 0
            counts[.sourceOmiAnalytics] = filterCounts.sources["omi-analytics"] ?? 0

            // Priority counts
            counts[.priorityHigh] = filterCounts.priorities["high"] ?? 0
            counts[.priorityMedium] = filterCounts.priorities["medium"] ?? 0
            counts[.priorityLow] = filterCounts.priorities["low"] ?? 0

            // Origin counts
            counts[.originDirectRequest] = filterCounts.origins["direct_request"] ?? 0
            counts[.originSelfGenerated] = filterCounts.origins["self_generated"] ?? 0
            counts[.originCalendarDriven] = filterCounts.origins["calendar_driven"] ?? 0
            counts[.originReactive] = filterCounts.origins["reactive"] ?? 0
            counts[.originExternalSystem] = filterCounts.origins["external_system"] ?? 0
            counts[.originOther] = filterCounts.origins["other"] ?? 0

            tagCounts = counts

            // Discover and count dynamic tags from SQLite data
            var newDynamicTags: [DynamicFilterTag] = []
            var newDynamicCounts: [String: Int] = [:]

            // Find unknown sources
            let knownSources = TaskFilterTag.knownSources
            for (source, count) in filterCounts.sources {
                if !knownSources.contains(source) && count > 0 {
                    let tag = DynamicFilterTag.source(source)
                    newDynamicTags.append(tag)
                    newDynamicCounts[tag.id] = count
                }
            }

            // Find unknown categories
            let knownCategories = TaskFilterTag.knownCategories
            for (category, count) in filterCounts.categories {
                if !knownCategories.contains(category) && count > 0 {
                    let tag = DynamicFilterTag.category(category)
                    newDynamicTags.append(tag)
                    newDynamicCounts[tag.id] = count
                }
            }

            // Sort by count descending
            newDynamicTags.sort { (newDynamicCounts[$0.id] ?? 0) > (newDynamicCounts[$1.id] ?? 0) }

            dynamicTags = newDynamicTags
            dynamicTagCounts = newDynamicCounts

        } catch {
            logError("TasksViewModel: Failed to load tag counts from database", error: error)
            // Fall back to in-memory counts
            let allTasks = store.incompleteTasks + store.completedTasks
            todoCount = store.incompleteTasks.count
            doneCount = store.completedTasks.count

            var counts: [TaskFilterTag: Int] = [:]
            for tag in TaskFilterTag.allCases {
                if tag == .removedByAI || tag == .removedByMe {
                    counts[tag] = store.deletedTasks.filter { tag.matches($0) }.count
                } else {
                    counts[tag] = allTasks.filter { tag.matches($0) }.count
                }
            }
            tagCounts = counts

            // Also discover dynamic tags from in-memory tasks
            discoverDynamicTags()
        }
    }

    /// Perform search against SQLite database
    private func performSearch() async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)

        if query.isEmpty {
            searchResults = []
            recomputeDisplayCaches()
            return
        }

        isSearching = true

        do {
            // Search across all tasks in SQLite
            let results = try await ActionItemStorage.shared.searchLocalActionItems(
                query: query,
                limit: 10000,
                completed: nil,  // Search all
                includeDeleted: selectedTags.contains(.removedByAI) || selectedTags.contains(.removedByMe)
            )
            searchResults = results
            log("TasksViewModel: Search found \(results.count) tasks for '\(query)'")
        } catch {
            logError("TasksViewModel: Search failed", error: error)
            searchResults = []
        }

        isSearching = false
        recomputeDisplayCaches()
    }

    /// Whether we're currently in a filtered/search mode
    var isInFilteredMode: Bool {
        !searchText.isEmpty || hasActiveFilters
    }

    /// Recompute display-related caches when filters or sort change
    private func recomputeDisplayCaches() {
        log("RENDER: recomputeDisplayCaches called")
        // Determine the source of tasks based on current state
        let sourceTasks: [TaskActionItem]

        if !searchText.isEmpty {
            // Searching: use search results from SQLite
            sourceTasks = searchResults
        } else if !filteredFromDatabase.isEmpty {
            // Non-status filters applied: use SQLite filtered results
            sourceTasks = filteredFromDatabase
        } else {
            // No filters or only status filters: use in-memory store arrays
            sourceTasks = getSourceTasks()
        }

        // Apply status filters to SQLite results (if needed)
        // Note: Non-status filters (including date) are already applied by SQLite query
        let hasSQLiteFilters = selectedTags.contains(where: { $0.group != .status && $0.group != .date })
        let hasDateFilters = selectedTags.contains(where: { $0.group == .date })
        let filterContext = TaskFilterTag.FilterContext()
        var filteredTasks: [TaskActionItem]
        if !searchText.isEmpty {
            filteredTasks = applyNonStatusTagFilters(sourceTasks, context: filterContext)
        } else if hasSQLiteFilters || hasDateFilters {
            // SQLite already filtered by category/source/priority/date
            // Just apply status filters (todo/done/deleted)
            filteredTasks = applyStatusFilters(sourceTasks)
        } else {
            filteredTasks = applyTagFilters(sourceTasks, context: filterContext)
        }

        // Sort
        let sorted = sortTasks(filteredTasks)

        // Apply display cap for filtered/search mode
        if isInFilteredMode {
            allFilteredDisplayTasks = sorted
            let capped = Array(sorted.prefix(displayLimit))
            displayTasks = deduplicateById(capped)
            hasMoreFilteredResults = sorted.count > displayLimit
        } else {
            allFilteredDisplayTasks = []
            hasMoreFilteredResults = false
            displayTasks = deduplicateById(sorted)
        }

        // Compute categorizedTasks for category view
        var result: [TaskCategory: [TaskActionItem]] = [:]
        for category in TaskCategory.allCases {
            result[category] = []
        }
        let calendar = Calendar.current
        let startOfToday = calendar.startOfDay(for: Date())
        let startOfTomorrow = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        let startOfDayAfterTomorrow = calendar.date(byAdding: .day, value: 2, to: startOfToday)!
        // Use exact 7-day offset from current time (matches Flutter: now.subtract(Duration(days: 7)))
        let sevenDaysAgo = Date().addingTimeInterval(-7 * 24 * 60 * 60)
        for task in displayTasks {
            // Skip incomplete tasks older than 7 days (matches Flutter _categorizeItems)
            if !task.completed {
                if let dueAt = task.dueAt {
                    if dueAt < sevenDaysAgo { continue }
                } else if task.createdAt < sevenDaysAgo {
                    continue
                }
            }
            let category = categoryFor(task: task, startOfTomorrow: startOfTomorrow, startOfDayAfterTomorrow: startOfDayAfterTomorrow)
            result[category, default: []].append(task)
        }
        categorizedTasks = result

        // Debug logging
        log("TasksViewModel: Categorized \(displayTasks.count) tasks - Today: \(result[.today]?.count ?? 0), Tomorrow: \(result[.tomorrow]?.count ?? 0), Later: \(result[.later]?.count ?? 0), No Deadline: \(result[.noDeadline]?.count ?? 0)")
    }

    /// Load more filtered/search results (pagination within already-queried results)
    func loadMoreFiltered() {
        displayLimit += 100
        let capped = Array(allFilteredDisplayTasks.prefix(displayLimit))
        displayTasks = deduplicateById(capped)
        hasMoreFilteredResults = allFilteredDisplayTasks.count > displayLimit

        // Recompute categorized tasks
        var result: [TaskCategory: [TaskActionItem]] = [:]
        for category in TaskCategory.allCases {
            result[category] = []
        }
        let calendar = Calendar.current
        let startOfToday = calendar.startOfDay(for: Date())
        let startOfTomorrow = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        let startOfDayAfterTomorrow = calendar.date(byAdding: .day, value: 2, to: startOfToday)!
        // Use exact 7-day offset from current time (matches Flutter: now.subtract(Duration(days: 7)))
        let sevenDaysAgo = Date().addingTimeInterval(-7 * 24 * 60 * 60)
        for task in displayTasks {
            // Skip incomplete tasks older than 7 days (matches Flutter _categorizeItems)
            if !task.completed {
                if let dueAt = task.dueAt {
                    if dueAt < sevenDaysAgo { continue }
                } else if task.createdAt < sevenDaysAgo {
                    continue
                }
            }
            let category = categoryFor(task: task, startOfTomorrow: startOfTomorrow, startOfDayAfterTomorrow: startOfDayAfterTomorrow)
            result[category, default: []].append(task)
        }
        categorizedTasks = result
    }

    /// Remove duplicate tasks by ID, keeping the first occurrence
    private func deduplicateById(_ tasks: [TaskActionItem]) -> [TaskActionItem] {
        var seen = Set<String>()
        return tasks.filter { seen.insert($0.id).inserted }
    }

    /// Apply only status filters (todo/done/deleted)
    private func applyStatusFilters(_ tasks: [TaskActionItem]) -> [TaskActionItem] {
        let statusTags = selectedTags.filter { $0.group == .status }
        guard !statusTags.isEmpty else { return tasks }

        return tasks.filter { task in
            if statusTags.contains(.removedByAI) && task.deleted == true && task.deletedBy != "user" { return true }
            if statusTags.contains(.removedByMe) && task.deleted == true && task.deletedBy == "user" { return true }
            if statusTags.contains(.done) && task.completed { return true }
            if statusTags.contains(.todo) && !task.completed && task.deleted != true { return true }
            return false
        }
    }

    /// Apply only date filters (e.g., last7Days) — used when SQLite handled other filters
    private func applyDateFilters(_ tasks: [TaskActionItem], context: TaskFilterTag.FilterContext) -> [TaskActionItem] {
        let dateTags = selectedTags.filter { $0.group == .date }
        guard !dateTags.isEmpty else { return tasks }
        return tasks.filter { task in
            dateTags.contains { $0.matches(task, context: context) }
        }
    }

    /// Apply only non-status tag filters (for search results which already include all statuses)
    private func applyNonStatusTagFilters(_ tasks: [TaskActionItem], context: TaskFilterTag.FilterContext) -> [TaskActionItem] {
        let nonStatusTags = selectedTags.filter { $0.group != .status }
        guard !nonStatusTags.isEmpty else { return tasks }

        let tagsByGroup = Dictionary(grouping: nonStatusTags) { $0.group }

        return tasks.filter { task in
            for (_, groupTags) in tagsByGroup {
                let matchesGroup = groupTags.contains { $0.matches(task, context: context) }
                if !matchesGroup { return false }
            }
            return true
        }
    }

    // MARK: - Category Helpers

    private func categoryFor(task: TaskActionItem, startOfTomorrow: Date, startOfDayAfterTomorrow: Date) -> TaskCategory {
        guard let dueAt = task.dueAt else {
            return .noDeadline
        }

        // Overdue and today's tasks go into "Today" category (like Flutter)
        if dueAt < startOfTomorrow {
            return .today
        } else if dueAt < startOfDayAfterTomorrow {
            return .tomorrow
        } else {
            return .later
        }
    }

    private func sortTasks(_ tasks: [TaskActionItem]) -> [TaskActionItem] {
        // Matches Python backend sort: due_at ASC (nulls last), created_at DESC (newest first)
        tasks.sorted { a, b in
            let aDue = a.dueAt ?? .distantFuture
            let bDue = b.dueAt ?? .distantFuture
            if aDue != bDue {
                return aDue < bDue
            }
            // Tie-breaker: created_at descending (newest first)
            return a.createdAt > b.createdAt
        }
    }

    // MARK: - Actions (delegate to shared store)

    func loadTasks() async {
        await store.loadTasks()
    }

    /// Throttled wrapper called from .onAppear — skips if called too recently
    func throttledLoadMoreIfNeeded(currentTask: TaskActionItem) async {
        let now = Date()
        guard now.timeIntervalSince(lastLoadMoreTime) >= loadMoreThrottleInterval else { return }
        lastLoadMoreTime = now
        await loadMoreIfNeeded(currentTask: currentTask)
    }

    func loadMoreIfNeeded(currentTask: TaskActionItem) async {
        guard !isLoadingMoreGuard else { return }
        isLoadingMoreGuard = true
        defer { isLoadingMoreGuard = false }

        if isInFilteredMode {
            // In filtered mode, check if we need to show more from already-queried results
            let hasMore = hasMoreFilteredResults
            guard hasMore else { return }

            let thresholdIndex = displayTasks.index(displayTasks.endIndex, offsetBy: -10, limitedBy: displayTasks.startIndex) ?? displayTasks.startIndex
            guard let taskIndex = displayTasks.firstIndex(where: { $0.id == currentTask.id }),
                  taskIndex >= thresholdIndex else {
                return
            }
            loadMoreFiltered()
        } else {
            await store.loadMoreIfNeeded(currentTask: currentTask)
        }
    }

    func toggleTask(_ task: TaskActionItem) async {
        log("TasksViewModel: toggleTask called for id=\(task.id)")
        removeFromDisplay(task.id)
        await store.toggleTask(task)
    }

    func deleteTask(_ task: TaskActionItem) async {
        removeFromDisplay(task.id)
        await store.deleteTask(task)
    }

    /// Delete with undo: saves to undo stack, shows toast, auto-dismisses after 5s
    func deleteTaskWithUndo(_ task: TaskActionItem) async {
        // Save to undo stack (cap at 10)
        undoStack.append(UndoableAction(task: task, timestamp: Date()))
        if undoStack.count > 10 {
            undoStack.removeFirst(undoStack.count - 10)
        }

        // Delete the task
        removeFromDisplay(task.id)
        await store.deleteTask(task)

        // Show toast and schedule auto-dismiss
        showUndoToast = true
        undoToastDismissTask?.cancel()
        undoToastDismissTask = Task {
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            if !Task.isCancelled {
                withAnimation(.easeOut(duration: 0.3)) {
                    showUndoToast = false
                    undoStack.removeAll()
                }
            }
        }
    }

    /// Undo the last delete: pops from stack, restores task
    func undoLastDelete() async {
        guard let lastAction = undoStack.popLast() else { return }

        await store.restoreTask(lastAction.task)

        // Re-insert into display
        displayTasks.insert(lastAction.task, at: 0)
        let cat = TaskCategory.today // Default; will be recategorized on next recompute
        if categorizedTasks[cat] != nil {
            categorizedTasks[cat]?.insert(lastAction.task, at: 0)
        }

        // Hide toast if stack is now empty
        if undoStack.isEmpty {
            undoToastDismissTask?.cancel()
            withAnimation(.easeOut(duration: 0.3)) {
                showUndoToast = false
            }
        } else {
            // Reset auto-dismiss timer
            undoToastDismissTask?.cancel()
            undoToastDismissTask = Task {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if !Task.isCancelled {
                    withAnimation(.easeOut(duration: 0.3)) {
                        showUndoToast = false
                        undoStack.removeAll()
                    }
                }
            }
        }
    }

    // MARK: - Surgical Display Updates

    /// Remove a single task from displayTasks without full recompute
    private func removeFromDisplay(_ taskId: String) {
        displayTasks.removeAll { $0.id == taskId }
        for category in TaskCategory.allCases {
            categorizedTasks[category]?.removeAll { $0.id == taskId }
        }
    }

    /// Update a single task in displayTasks without full recompute
    private func updateInDisplay(_ updated: TaskActionItem) {
        if let index = displayTasks.firstIndex(where: { $0.id == updated.id }) {
            displayTasks[index] = updated
        }
        for category in TaskCategory.allCases {
            if let index = categorizedTasks[category]?.firstIndex(where: { $0.id == updated.id }) {
                categorizedTasks[category]?[index] = updated
            }
        }
    }

    // MARK: - Multi-Select

    func toggleMultiSelectMode() {
        isMultiSelectMode.toggle()
        if !isMultiSelectMode {
            selectedTaskIds.removeAll()
        }
    }

    func toggleTaskSelection(_ task: TaskActionItem) {
        if selectedTaskIds.contains(task.id) {
            selectedTaskIds.remove(task.id)
        } else {
            selectedTaskIds.insert(task.id)
        }
    }

    func selectAll() {
        selectedTaskIds = Set(displayTasks.map { $0.id })
    }

    func deselectAll() {
        selectedTaskIds.removeAll()
    }

    func deleteSelectedTasks() async {
        let idsToDelete = Array(selectedTaskIds)
        await store.deleteMultipleTasks(ids: idsToDelete)
        selectedTaskIds.removeAll()
        isMultiSelectMode = false
    }

    func createTask(description: String, dueAt: Date?, priority: String?, tags: [String]? = nil) async {
        await store.createTask(description: description, dueAt: dueAt, priority: priority, tags: tags)
        showingCreateTask = false
    }

    func updateTaskDetails(_ task: TaskActionItem, description: String? = nil, dueAt: Date? = nil, priority: String? = nil, recurrenceRule: String? = nil) async {
        await store.updateTask(task, description: description, dueAt: dueAt, priority: priority, recurrenceRule: recurrenceRule)
        // Read the updated task back from the store for surgical update
        if let updated = store.tasks.first(where: { $0.id == task.id }) {
            updateInDisplay(updated)
        }
    }

    // MARK: - Inline Task Creation

    /// Determine context (due date, tags) for a new inline task based on selected task position
    func contextForInlineCreate() -> (dueAt: Date?, tags: [String]) {
        let tags = selectedTags.compactMap { $0.categoryValue }
        guard let selectedId = keyboardSelectedTaskId else { return (nil, tags) }

        // Determine category of selected task
        for category in TaskCategory.allCases {
            if categorizedTasks[category]?.contains(where: { $0.id == selectedId }) == true {
                return (dueAtForCategory(category), tags)
            }
        }
        // Flat view: inherit from selected task
        if let task = displayTasks.first(where: { $0.id == selectedId }) {
            return (task.dueAt, tags)
        }
        return (nil, tags)
    }

    private func dueAtForCategory(_ category: TaskCategory) -> Date? {
        let cal = Calendar.current
        let startOfToday = cal.startOfDay(for: Date())
        switch category {
        case .today: return cal.date(bySettingHour: 23, minute: 59, second: 0, of: Date())
        case .tomorrow: return cal.date(byAdding: .day, value: 1, to: startOfToday)
        case .later: return cal.date(byAdding: .day, value: 7, to: startOfToday)
        case .noDeadline: return nil
        }
    }

    /// Create an inline task below the specified task
    func createInlineTask(description: String, afterTaskId: String?) async {
        let context = contextForInlineCreate()
        let created = await store.createTask(
            description: description,
            dueAt: context.dueAt,
            priority: nil,
            tags: context.tags.isEmpty ? nil : context.tags
        )

        // Position the new task after afterTaskId in category order
        if let created = created, let afterId = afterTaskId {
            for category in TaskCategory.allCases {
                if let tasks = categorizedTasks[category],
                   let afterIndex = tasks.firstIndex(where: { $0.id == afterId }) {
                    moveTask(created, toIndex: afterIndex + 1, inCategory: category)
                    break
                }
            }
            // Select the newly created task
            keyboardSelectedTaskId = created.id
        }

        isInlineCreating = false
        inlineCreateAfterTaskId = nil
    }
}

// MARK: - Tasks Page

struct TasksPage: View {
    @ObservedObject var viewModel: TasksViewModel
    var chatProvider: ChatProvider?

    // Chat panel state
    @StateObject private var chatCoordinator: TaskChatCoordinator
    @State private var showChatPanel = false
    @AppStorage("tasksChatPanelWidth") private var chatPanelWidth: Double = 400
    /// The window width before the chat panel was opened, so we can restore it exactly.
    /// Persisted so we can restore on app relaunch if the user quit with chat open.
    @AppStorage("tasksPreChatWindowWidth") private var preChatWindowWidth: Double = 0

    // Keyboard navigation state
    @State private var inlineCreateText = ""
    @FocusState private var inlineCreateFocused: Bool
    @State private var keyboardMonitor: Any?

    // Filter popover state
    @State private var showFilterPopover = false
    @State private var pendingSelectedTags: Set<TaskFilterTag> = [.todo, .last7Days]
    @State private var pendingSelectedDynamicTags: Set<DynamicFilterTag> = []
    @State private var filterSearchText = ""

    // Save filter view state
    @State private var showSaveFilterAlert = false
    @State private var saveFilterName = ""

    // Chat panel resize state
    @State private var isDraggingDivider = false
    @State private var dragStartWidth: Double = 0

    init(viewModel: TasksViewModel, chatProvider: ChatProvider? = nil) {
        self.viewModel = viewModel
        self.chatProvider = chatProvider
        let provider = chatProvider ?? ChatProvider()
        _chatCoordinator = StateObject(wrappedValue: TaskChatCoordinator(chatProvider: provider))
    }

    var body: some View {
        let isChatVisible = showChatPanel

        HStack(spacing: 0) {
            // Left panel: Tasks content (always full width)
            tasksContent
                .frame(maxWidth: .infinity)

            if isChatVisible {
                // Draggable divider
                Rectangle()
                    .fill(isDraggingDivider ? OmiColors.textSecondary : OmiColors.border)
                    .frame(width: 1)
                    .contentShape(Rectangle().inset(by: -4))
                    .onHover { hovering in
                        if hovering {
                            NSCursor.resizeLeftRight.push()
                        } else {
                            NSCursor.pop()
                        }
                    }
                    .gesture(
                        DragGesture(coordinateSpace: .global)
                            .onChanged { value in
                                isDraggingDivider = true
                                if dragStartWidth == 0 {
                                    dragStartWidth = chatPanelWidth
                                }
                                let delta = value.startLocation.x - value.location.x
                                chatPanelWidth = min(600, max(300, dragStartWidth + delta))
                            }
                            .onEnded { _ in
                                isDraggingDivider = false
                                dragStartWidth = 0
                            }
                    )

                // Right panel: Task chat (slides in from right)
                Group {
                    if let taskState = chatCoordinator.activeTaskState {
                        TaskChatPanel(
                            taskState: taskState,
                            coordinator: chatCoordinator,
                            task: activeTask,
                            onClose: {
                                closeChatPanel()
                            }
                        )
                    } else {
                        // No task selected — show empty panel with close button
                        TaskChatPanelPlaceholder(
                            coordinator: chatCoordinator,
                            onClose: { closeChatPanel() }
                        )
                    }
                }
                .frame(width: chatPanelWidth)
                .transition(.move(edge: .trailing))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .dismissableSheet(isPresented: $viewModel.showingCreateTask) {
            TaskCreateSheet(
                viewModel: viewModel,
                onDismiss: { viewModel.showingCreateTask = false }
            )
        }
        .onAppear {
            // If tasks are already loaded, notify sidebar to clear loading indicator
            if !viewModel.isLoading {
                NotificationCenter.default.post(name: .tasksPageDidLoad, object: nil)
            }
            // Ensure prioritization service is running (no-op if already started)
            Task { await TaskPrioritizationService.shared.start() }

            // Shrink window if it was left expanded from a previous session with chat open.
            // Delay slightly so the window is fully visible before resizing.
            if !showChatPanel {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    shrinkWindowIfNeeded()
                }
            }
        }
        .onDisappear {
            // Reset chat state and shrink window when navigating away from Tasks tab
            if showChatPanel {
                adjustWindowWidth(expand: false)
                showChatPanel = false
                chatCoordinator.closeChat()
            }
        }
    }

    /// The currently active task for the chat panel
    private var activeTask: TaskActionItem? {
        guard let taskId = chatCoordinator.activeTaskId else { return nil }
        return viewModel.findTask(taskId)
    }

    /// Open chat for a task
    private func openChatForTask(_ task: TaskActionItem) {
        log("TaskChat: openChatForTask called for task \(task.id) (deleted=\(task.deleted ?? false), completed=\(task.completed))")
        if !showChatPanel {
            // First open: expand window and reveal the panel together
            adjustWindowWidth(expand: true)
            withAnimation(.easeInOut(duration: 0.25)) {
                showChatPanel = true
            }
        }
        // Switch to (or start) chat for this task
        Task {
            await chatCoordinator.openChat(for: task)
        }
    }

    /// Close the chat panel and shrink window
    private func closeChatPanel() {
        chatCoordinator.closeChat()
        // Animate panel out and shrink window together
        withAnimation(.easeInOut(duration: 0.25)) {
            showChatPanel = false
        }
        // Shrink window after a short delay so the slide-out animation is visible
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            adjustWindowWidth(expand: false)
        }
    }

    /// Expand or shrink the main window to accommodate the chat panel.
    /// Saves the user's original width before expanding so it can be restored exactly.
    private func adjustWindowWidth(expand: Bool) {
        guard let window = NSApp.windows.first(where: { $0.title.hasPrefix("Omi") && $0.isVisible }) else { return }

        let expandAmount = chatPanelWidth + 1 // +1 for divider
        var frame = window.frame

        if expand {
            // Remember the user's current width before we change it
            preChatWindowWidth = frame.size.width
            frame.size.width += expandAmount
            // Clamp to screen bounds
            if let screen = window.screen {
                let maxRight = screen.visibleFrame.maxX
                if frame.maxX > maxRight {
                    frame.origin.x = maxRight - frame.size.width
                }
            }
        } else {
            // Restore to the saved width, or just subtract the expand amount
            if preChatWindowWidth > 0 {
                frame.size.width = preChatWindowWidth
                preChatWindowWidth = 0
            } else {
                frame.size.width -= expandAmount
            }
        }

        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.25
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            window.animator().setFrame(frame, display: true)
        }
    }

    /// On launch, restore the window to its pre-chat width if the user quit with chat open.
    /// Uses no animation since the app is just opening.
    private func shrinkWindowIfNeeded() {
        guard preChatWindowWidth > 0 else { return }
        guard let window = NSApp.windows.first(where: { $0.title.hasPrefix("Omi") && $0.isVisible }) else { return }
        var frame = window.frame
        frame.size.width = preChatWindowWidth
        window.setFrame(frame, display: true)
        preChatWindowWidth = 0
    }

    // MARK: - Tasks Content

    private var tasksContent: some View {
        VStack(spacing: 0) {
            // Header with filter toggle and sort
            headerView

            // Content
            if viewModel.isLoading && viewModel.tasks.isEmpty {
                loadingView
            } else if let error = viewModel.error, viewModel.tasks.isEmpty {
                errorView(error)
            } else if viewModel.displayTasks.isEmpty {
                emptyView
            } else {
                tasksListView
            }
        }
        .overlay(alignment: .bottom) {
            VStack(spacing: 8) {
                Spacer()
                // Keyboard hint bar
                if !viewModel.displayTasks.isEmpty {
                    KeyboardHintBar(
                        isAnyTaskEditing: viewModel.isAnyTaskEditing,
                        isInlineCreating: viewModel.isInlineCreating,
                        hasSelection: viewModel.keyboardSelectedTaskId != nil
                    )
                    .transition(.opacity)
                    .animation(.easeInOut(duration: 0.15), value: viewModel.keyboardSelectedTaskId)
                    .animation(.easeInOut(duration: 0.15), value: viewModel.isInlineCreating)
                }
                // Undo toast
                if viewModel.showUndoToast, let lastAction = viewModel.undoStack.last {
                    UndoToastView(
                        taskDescription: lastAction.task.description,
                        undoCount: viewModel.undoStack.count,
                        onUndo: { Task { await viewModel.undoLastDelete() } }
                    )
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .padding(.bottom, 16)
            .animation(.easeInOut(duration: 0.25), value: viewModel.showUndoToast)
        }
        .onAppear {
            installKeyboardMonitor()
        }
        .onDisappear {
            removeKeyboardMonitor()
        }
        .onChange(of: viewModel.isInlineCreating) { _, isCreating in
            if isCreating {
                // Keyboard triggered inline create — reset text and focus
                inlineCreateText = ""
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    inlineCreateFocused = true
                }
            } else {
                // Cancelled — clear text and unfocus
                inlineCreateText = ""
                inlineCreateFocused = false
            }
        }
    }

    // MARK: - Keyboard Event Monitor

    private func installKeyboardMonitor() {
        guard keyboardMonitor == nil else { return }
        let vm = viewModel
        keyboardMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            return vm.handleKeyDown(event) ? nil : event
        }
    }

    private func removeKeyboardMonitor() {
        if let monitor = keyboardMonitor {
            NSEvent.removeMonitor(monitor)
            keyboardMonitor = nil
        }
    }

    // MARK: - Keyboard Navigation Helpers

    private func selectTask(_ task: TaskActionItem) {
        viewModel.keyboardSelectedTaskId = task.id
    }

    private func cancelInlineCreate() {
        viewModel.isInlineCreating = false
        viewModel.inlineCreateAfterTaskId = nil
        inlineCreateText = ""
        inlineCreateFocused = false
    }

    private func commitInlineCreate() {
        let text = inlineCreateText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            cancelInlineCreate()
            return
        }
        let afterId = viewModel.inlineCreateAfterTaskId
        inlineCreateText = ""
        inlineCreateFocused = false
        Task {
            await viewModel.createInlineTask(description: text, afterTaskId: afterId)
        }
    }

    // MARK: - Header View

    private var headerView: some View {
        HStack(spacing: 10) {
            // Search field
            HStack(spacing: 8) {
                if viewModel.isSearching || viewModel.isLoadingFiltered {
                    ProgressView()
                        .scaleEffect(0.7)
                        .frame(width: 14, height: 14)
                } else {
                    Image(systemName: "magnifyingglass")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }

                TextField("Search tasks...", text: $viewModel.searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(OmiColors.textPrimary)

                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(8)

            // Saved filter view chips
            if !viewModel.savedFilterViews.isEmpty && !viewModel.isMultiSelectMode {
                ForEach(viewModel.savedFilterViews) { savedView in
                    let isActive = viewModel.isActiveSavedView(savedView)
                    Button {
                        viewModel.applySavedView(savedView)
                    } label: {
                        Text(savedView.name)
                            .scaledFont(size: 11, weight: .medium)
                            .foregroundColor(isActive ? .white : OmiColors.textSecondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(isActive ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
                            .cornerRadius(6)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(isActive ? OmiColors.border : Color.clear, lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        Button(role: .destructive) {
                            viewModel.deleteSavedView(savedView)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
            }

            if !viewModel.isMultiSelectMode {
                // Save current filters button
                if viewModel.hasNonDefaultFilters {
                    saveFilterButton
                }
                filterDropdownButton
            } else {
                multiSelectControls
            }

            if viewModel.isMultiSelectMode {
                if !viewModel.selectedTaskIds.isEmpty {
                    deleteSelectedButton
                }
                cancelMultiSelectButton
            } else {
                addTaskButton
                if chatProvider != nil && TaskAgentSettings.shared.isEnabled {
                    chatToggleButton
                }
                taskSettingsButton
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 12)
        .alert("Save Filter View", isPresented: $showSaveFilterAlert) {
            TextField("View name", text: $saveFilterName)
            Button("Save") {
                let name = saveFilterName.trimmingCharacters(in: .whitespacesAndNewlines)
                if !name.isEmpty {
                    viewModel.saveCurrentFilters(name: name)
                }
                saveFilterName = ""
            }
            Button("Cancel", role: .cancel) {
                saveFilterName = ""
            }
        } message: {
            Text("Enter a name for this filter combination.")
        }
    }

    private var saveFilterButton: some View {
        Button {
            saveFilterName = ""
            showSaveFilterAlert = true
        } label: {
            Image(systemName: "bookmark")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(8)
        }
        .buttonStyle(.plain)
        .help("Save current filters as a view")
    }

    // MARK: - Filter Dropdown

    private var filterLabel: String {
        let totalCount = viewModel.selectedTags.count + viewModel.selectedDynamicTags.count
        if totalCount == 0 {
            return "All"
        } else if viewModel.selectedTags == [.todo, .last7Days] && viewModel.selectedDynamicTags.isEmpty {
            return "To Do"
        } else if totalCount == 1 {
            if let tag = viewModel.selectedTags.first {
                return tag.displayName
            } else if let dynamicTag = viewModel.selectedDynamicTags.first {
                return dynamicTag.displayName
            }
            return "1 selected"
        } else {
            return "\(totalCount) selected"
        }
    }

    /// Filtered predefined tags based on search text, grouped by filter group
    private func filteredTags(for group: TaskFilterGroup) -> [TaskFilterTag] {
        let tags = TaskFilterTag.tags(for: group)
        if filterSearchText.isEmpty {
            return tags.sorted { viewModel.tagCount($0) > viewModel.tagCount($1) }
        }
        return tags
            .filter { $0.displayName.localizedCaseInsensitiveContains(filterSearchText) }
            .sorted { viewModel.tagCount($0) > viewModel.tagCount($1) }
    }

    /// Filtered dynamic tags based on search text, grouped by filter group
    private func filteredDynamicTags(for group: TaskFilterGroup) -> [DynamicFilterTag] {
        let tags = viewModel.dynamicTags.filter { $0.group == group }
        if filterSearchText.isEmpty {
            return tags.sorted { viewModel.dynamicTagCount($0) > viewModel.dynamicTagCount($1) }
        }
        return tags
            .filter { $0.displayName.localizedCaseInsensitiveContains(filterSearchText) }
            .sorted { viewModel.dynamicTagCount($0) > viewModel.dynamicTagCount($1) }
    }

    private var filterDropdownButton: some View {
        Button {
            pendingSelectedTags = viewModel.selectedTags
            pendingSelectedDynamicTags = viewModel.selectedDynamicTags
            filterSearchText = ""
            showFilterPopover = true
        } label: {
            Image(systemName: "line.3.horizontal.decrease")
                .scaledFont(size: 12)
            .foregroundColor(viewModel.hasActiveFilters ? OmiColors.textPrimary : OmiColors.textSecondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(viewModel.hasActiveFilters ? OmiColors.border : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showFilterPopover, arrowEdge: .bottom) {
            filterPopover
        }
    }

    private var filterPopover: some View {
        VStack(spacing: 0) {
            // Search field
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(OmiColors.textTertiary)
                    .scaledFont(size: 12)

                TextField("Search filters...", text: $filterSearchText)
                    .textFieldStyle(.plain)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textPrimary)

                if !filterSearchText.isEmpty {
                    Button {
                        filterSearchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                            .scaledFont(size: 12)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(6)
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 8)

            Divider()
                .padding(.horizontal, 12)

            // Tag list grouped by filter group
            ScrollView {
                VStack(spacing: 2) {
                    // "All" option
                    Button {
                        pendingSelectedTags.removeAll()
                        pendingSelectedDynamicTags.removeAll()
                    } label: {
                        HStack {
                            Image(systemName: "tray.full")
                                .scaledFont(size: 12)
                                .frame(width: 20)
                            Text("All")
                                .scaledFont(size: 13)
                            Spacer()
                            Text("\(viewModel.todoCount + viewModel.doneCount)")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(OmiColors.backgroundTertiary)
                                .cornerRadius(4)
                            if pendingSelectedTags.isEmpty && pendingSelectedDynamicTags.isEmpty {
                                Image(systemName: "checkmark")
                                    .scaledFont(size: 12, weight: .medium)
                                    .foregroundColor(.white)
                            }
                        }
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(pendingSelectedTags.isEmpty && pendingSelectedDynamicTags.isEmpty ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
                        .cornerRadius(6)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    // Groups
                    ForEach(TaskFilterGroup.allCases, id: \.self) { group in
                        let tags = filteredTags(for: group)
                        let dynTags = filteredDynamicTags(for: group)
                        if !tags.isEmpty || !dynTags.isEmpty {
                            Divider()
                                .padding(.vertical, 4)

                            // Group header
                            Text(group.rawValue)
                                .scaledFont(size: 11, weight: .semibold)
                                .foregroundColor(OmiColors.textTertiary)
                                .textCase(.uppercase)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 4)
                                .frame(maxWidth: .infinity, alignment: .leading)

                            // Predefined tags in group
                            ForEach(tags) { tag in
                                let isSelected = pendingSelectedTags.contains(tag)
                                let count = viewModel.tagCount(tag)

                                Button {
                                    if isSelected {
                                        pendingSelectedTags.remove(tag)
                                    } else {
                                        pendingSelectedTags.insert(tag)
                                    }
                                } label: {
                                    HStack {
                                        Image(systemName: tag.icon)
                                            .scaledFont(size: 12)
                                            .frame(width: 20)
                                        Text(tag.displayName)
                                            .scaledFont(size: 13)
                                        Spacer()
                                        Text("\(count)")
                                            .scaledFont(size: 11)
                                            .foregroundColor(OmiColors.textTertiary)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(OmiColors.backgroundTertiary)
                                            .cornerRadius(4)
                                        if isSelected {
                                            Image(systemName: "checkmark")
                                                .scaledFont(size: 12, weight: .medium)
                                                .foregroundColor(.white)
                                        }
                                    }
                                    .foregroundColor(OmiColors.textPrimary)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(isSelected ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
                                    .cornerRadius(6)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }

                            // Dynamic tags for this group (discovered from task data)
                            ForEach(filteredDynamicTags(for: group)) { tag in
                                let isSelected = pendingSelectedDynamicTags.contains(tag)
                                let count = viewModel.dynamicTagCount(tag)

                                Button {
                                    if isSelected {
                                        pendingSelectedDynamicTags.remove(tag)
                                    } else {
                                        pendingSelectedDynamicTags.insert(tag)
                                    }
                                } label: {
                                    HStack {
                                        Image(systemName: tag.icon)
                                            .scaledFont(size: 12)
                                            .frame(width: 20)
                                        Text(tag.displayName)
                                            .scaledFont(size: 13)
                                        Spacer()
                                        Text("\(count)")
                                            .scaledFont(size: 11)
                                            .foregroundColor(OmiColors.textTertiary)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(OmiColors.backgroundTertiary)
                                            .cornerRadius(4)
                                        if isSelected {
                                            Image(systemName: "checkmark")
                                                .scaledFont(size: 12, weight: .medium)
                                                .foregroundColor(.white)
                                        }
                                    }
                                    .foregroundColor(OmiColors.textPrimary)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(isSelected ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
                                    .cornerRadius(6)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
            .frame(maxHeight: 350)

            Divider()
                .padding(.horizontal, 12)

            // Action buttons
            HStack(spacing: 8) {
                Button {
                    pendingSelectedTags.removeAll()
                    pendingSelectedDynamicTags.removeAll()
                } label: {
                    Text("Clear")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(OmiColors.backgroundTertiary)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)

                Button {
                    viewModel.selectedTags = pendingSelectedTags
                    viewModel.selectedDynamicTags = pendingSelectedDynamicTags
                    showFilterPopover = false
                } label: {
                    Text("Apply")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(.black)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color.white)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(12)
        }
        .frame(width: 280)
    }

    private var multiSelectControls: some View {
        HStack(spacing: 12) {
            Button {
                if viewModel.selectedTaskIds.count == viewModel.displayTasks.count {
                    viewModel.deselectAll()
                } else {
                    viewModel.selectAll()
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: viewModel.selectedTaskIds.count == viewModel.displayTasks.count ? "checkmark.circle.fill" : "circle")
                        .scaledFont(size: 14)
                    Text(viewModel.selectedTaskIds.count == viewModel.displayTasks.count ? "Deselect All" : "Select All")
                        .scaledFont(size: 13, weight: .medium)
                }
                .foregroundColor(OmiColors.textSecondary)
            }
            .buttonStyle(.plain)

            Text("\(viewModel.selectedTaskIds.count) selected")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private var deleteSelectedButton: some View {
        Button {
            Task {
                await viewModel.deleteSelectedTasks()
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "trash")
                    .scaledFont(size: 12)
                Text("Delete \(viewModel.selectedTaskIds.count)")
                    .scaledFont(size: 13, weight: .medium)
            }
            .foregroundColor(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.red)
            )
        }
        .buttonStyle(.plain)
    }

    private var cancelMultiSelectButton: some View {
        Button {
            viewModel.toggleMultiSelectMode()
        } label: {
            Text("Cancel")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundSecondary)
                )
        }
        .buttonStyle(.plain)
    }

    private var addTaskButton: some View {
        Button {
            viewModel.showingCreateTask = true
        } label: {
            Image(systemName: "plus")
                .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(.black)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.white)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(OmiColors.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }


    private var taskSettingsButton: some View {
        Button {
            NotificationCenter.default.post(
                name: .navigateToTaskSettings,
                object: nil
            )
        } label: {
            Image(systemName: "gearshape")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundSecondary)
                )
        }
        .buttonStyle(.plain)
        .help("Task Settings")
    }

    private var chatToggleButton: some View {
        Button {
            if showChatPanel {
                closeChatPanel()
            } else {
                // Open empty sidebar — user picks a task to chat about
                adjustWindowWidth(expand: true)
                withAnimation(.easeInOut(duration: 0.25)) {
                    showChatPanel = true
                }
            }
        } label: {
            Image(systemName: showChatPanel ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                .scaledFont(size: 12)
                .foregroundColor(showChatPanel ? OmiColors.purplePrimary : OmiColors.textSecondary)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(showChatPanel ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundSecondary)
                )
        }
        .buttonStyle(.plain)
        .help(showChatPanel ? "Close chat panel" : "Open task chat")
    }

    // MARK: - Loading View

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)
                .tint(OmiColors.textSecondary)

            Text("Loading tasks...")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Error View

    private func errorView(_ error: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("Failed to load tasks")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text(error)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button("Try Again") {
                Task {
                    await viewModel.loadTasks()
                }
            }
            .buttonStyle(.bordered)
            .tint(OmiColors.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Empty View

    private var emptyView: some View {
        VStack(spacing: 16) {
            Image(systemName: viewModel.hasActiveFilters ? "line.3.horizontal.decrease" : "tray.fill")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text(viewModel.hasActiveFilters ? "No Matching Tasks" : "All Caught Up!")
                .scaledFont(size: 24, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text(viewModel.hasActiveFilters ? "Try adjusting your filters" : "You have no tasks yet")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)

            if viewModel.hasActiveFilters {
                Button("Clear Filters") {
                    withAnimation {
                        viewModel.clearAllFilters()
                    }
                }
                .buttonStyle(.bordered)
                .tint(OmiColors.textSecondary)
                .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Tasks List View

    private var tasksListView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    // Show tasks grouped by due-date category (Today, Tomorrow, Later, No Deadline)
                    let onlyDone = viewModel.selectedTags.contains(.done) && !viewModel.selectedTags.contains(.todo)
                    let onlyDeleted = (viewModel.selectedTags.contains(.removedByAI) || viewModel.selectedTags.contains(.removedByMe)) && !viewModel.selectedTags.contains(.todo) && !viewModel.selectedTags.contains(.done)
                    if !onlyDone && !onlyDeleted && !viewModel.isMultiSelectMode {
                        ForEach(TaskCategory.allCases, id: \.self) { category in
                            let orderedTasks = viewModel.getOrderedTasks(for: category)
                            if !orderedTasks.isEmpty {
                                TaskCategorySection(
                                    category: category,
                                    orderedTasks: orderedTasks,
                                    isMultiSelectMode: viewModel.isMultiSelectMode,
                                    indentLevelFor: { viewModel.getIndentLevel(for: $0) },
                                    isSelectedFor: { viewModel.selectedTaskIds.contains($0) },
                                    isKeyboardSelectedFor: { viewModel.keyboardSelectedTaskId == $0 },
                                    onToggle: { await viewModel.toggleTask($0) },
                                    onDelete: { await viewModel.deleteTaskWithUndo($0) },
                                    onToggleSelection: { viewModel.toggleTaskSelection($0) },
                                    onUpdateDetails: { task, desc, date, priority, recurrenceRule in
                                        await viewModel.updateTaskDetails(task, description: desc, dueAt: date, priority: priority, recurrenceRule: recurrenceRule)
                                    },
                                    onIncrementIndent: { viewModel.incrementIndent(for: $0) },
                                    onDecrementIndent: { viewModel.decrementIndent(for: $0) },
                                    onMoveTask: { task, index, cat in viewModel.moveTask(task, toIndex: index, inCategory: cat) },
                                    onOpenChat: chatProvider != nil ? { task in openChatForTask(task) } : nil,
                                    onSelect: { task in selectTask(task) },
                                    onHover: { viewModel.hoveredTaskId = $0 },
                                    isChatActive: showChatPanel,
                                    activeChatTaskId: chatCoordinator.activeTaskId,
                                    chatCoordinator: chatCoordinator,
                                    editingTaskId: viewModel.editingTaskId,
                                    onEditingChanged: { editing in
                                        viewModel.isAnyTaskEditing = editing
                                        if !editing { viewModel.editingTaskId = nil }
                                    },
                                    animateToggleTaskId: viewModel.animateToggleTaskId,
                                    isInlineCreating: viewModel.isInlineCreating,
                                    inlineCreateAfterTaskId: viewModel.inlineCreateAfterTaskId,
                                    inlineCreateText: $inlineCreateText,
                                    inlineCreateFocused: $inlineCreateFocused,
                                    onInlineCommit: { commitInlineCreate() },
                                    onInlineCancel: { cancelInlineCreate() }
                                )
                            }
                        }
                    } else {
                        // Flat list for other sort options, completed view, or multi-select mode
                        ForEach(viewModel.displayTasks) { task in
                            VStack(spacing: 0) {
                                TaskRow(
                                    task: task,
                                    indentLevel: viewModel.getIndentLevel(for: task.id),
                                    isMultiSelectMode: viewModel.isMultiSelectMode,
                                    isSelected: viewModel.selectedTaskIds.contains(task.id),
                                    isKeyboardSelected: viewModel.keyboardSelectedTaskId == task.id,
                                    onToggle: { await viewModel.toggleTask($0) },
                                    onDelete: { await viewModel.deleteTaskWithUndo($0) },
                                    onToggleSelection: { viewModel.toggleTaskSelection($0) },
                                    onUpdateDetails: { task, desc, date, priority, recurrenceRule in
                                        await viewModel.updateTaskDetails(task, description: desc, dueAt: date, priority: priority, recurrenceRule: recurrenceRule)
                                    },
                                    onIncrementIndent: { viewModel.incrementIndent(for: $0) },
                                    onDecrementIndent: { viewModel.decrementIndent(for: $0) },
                                    onOpenChat: chatProvider != nil ? { task in openChatForTask(task) } : nil,
                                    onSelect: { task in selectTask(task) },
                                    onHover: { viewModel.hoveredTaskId = $0 },
                                    isChatActive: showChatPanel,
                                    activeChatTaskId: chatCoordinator.activeTaskId,
                                    chatCoordinator: chatCoordinator,
                                    editingTaskId: viewModel.editingTaskId,
                                    onEditingChanged: { editing in
                                        viewModel.isAnyTaskEditing = editing
                                        if !editing { viewModel.editingTaskId = nil }
                                    },
                                    animateToggleTaskId: viewModel.animateToggleTaskId
                                )
                                .id(task.id)

                                // Inline creation row (flat view)
                                if viewModel.isInlineCreating && viewModel.inlineCreateAfterTaskId == task.id {
                                    InlineTaskCreationRow(
                                        text: $inlineCreateText,
                                        isFocused: $inlineCreateFocused,
                                        onCommit: { _ in commitInlineCreate() },
                                        onCancel: { cancelInlineCreate() }
                                    )
                                    .padding(.top, 4)
                                }
                            }
                            .onAppear {
                                Task {
                                    await viewModel.throttledLoadMoreIfNeeded(currentTask: task)
                                }
                            }
                        }
                    }

                    // Loading more indicator
                    if viewModel.isLoadingMore {
                        HStack {
                            Spacer()
                            ProgressView()
                                .controlSize(.small)
                            Spacer()
                        }
                        .padding(.vertical, 12)
                    }

                    // "Load more" button
                    if !viewModel.displayTasks.isEmpty && !viewModel.isLoadingMore {
                        if viewModel.isInFilteredMode && viewModel.hasMoreFilteredResults {
                            Button {
                                viewModel.loadMoreFiltered()
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "arrow.down.circle")
                                    Text("Load more tasks")
                                }
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(OmiColors.backgroundTertiary)
                                .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                        } else if !viewModel.isInFilteredMode && viewModel.hasMoreTasks {
                            Button {
                                Task { await viewModel.loadMoreIfNeeded(currentTask: viewModel.displayTasks.last!) }
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "arrow.down.circle")
                                    Text("Load more tasks")
                                }
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(OmiColors.backgroundTertiary)
                                .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .refreshable {
                await viewModel.loadTasks()
            }
            .onAppear { viewModel.scrollProxy = proxy }
        }
    }
}

// MARK: - Task Category Section

struct TaskCategorySection: View {
    let category: TaskCategory
    let orderedTasks: [TaskActionItem]
    var isMultiSelectMode: Bool = false

    // Callbacks for row data and actions (passed through to TaskRow)
    var indentLevelFor: ((String) -> Int)?
    var isSelectedFor: ((String) -> Bool)?
    var isKeyboardSelectedFor: ((String) -> Bool)?
    var onToggle: ((TaskActionItem) async -> Void)?
    var onDelete: ((TaskActionItem) async -> Void)?
    var onToggleSelection: ((TaskActionItem) -> Void)?
    var onUpdateDetails: ((TaskActionItem, String?, Date?, String?, String?) async -> Void)?
    var onIncrementIndent: ((String) -> Void)?
    var onDecrementIndent: ((String) -> Void)?
    var onMoveTask: ((TaskActionItem, Int, TaskCategory) -> Void)?
    var onOpenChat: ((TaskActionItem) -> Void)?
    var onSelect: ((TaskActionItem) -> Void)?
    var onHover: ((String?) -> Void)?
    var isChatActive: Bool = false
    var activeChatTaskId: String?
    var chatCoordinator: TaskChatCoordinator?

    // Edit mode support
    var editingTaskId: String?
    var onEditingChanged: ((Bool) -> Void)?

    // Space-key animated toggle
    var animateToggleTaskId: String?

    // Inline creation support
    var isInlineCreating: Bool = false
    var inlineCreateAfterTaskId: String?
    @Binding var inlineCreateText: String
    @FocusState.Binding var inlineCreateFocused: Bool
    var onInlineCommit: (() -> Void)?
    var onInlineCancel: (() -> Void)?

    private var visibleTasks: [TaskActionItem] {
        orderedTasks
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Category header
            HStack(spacing: 8) {
                Image(systemName: category.icon)
                    .scaledFont(size: 14)
                    .foregroundColor(category.color)

                Text(category.rawValue)
                    .scaledFont(size: 15, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("\(orderedTasks.count)")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(OmiColors.textTertiary.opacity(0.1))
                    )

                Spacer()
            }
            .padding(.horizontal, 4)

            // Tasks in category with drag-and-drop reordering
            if !isMultiSelectMode {
                LazyVStack(spacing: 8) {
                    ForEach(visibleTasks) { task in
                        VStack(spacing: 0) {
                            TaskRow(
                                task: task,
                                category: category,
                                indentLevel: indentLevelFor?(task.id) ?? 0,
                                isMultiSelectMode: isMultiSelectMode,
                                isSelected: isSelectedFor?(task.id) ?? false,
                                isKeyboardSelected: isKeyboardSelectedFor?(task.id) ?? false,
                                onToggle: onToggle,
                                onDelete: onDelete,
                                onToggleSelection: onToggleSelection,
                                onUpdateDetails: onUpdateDetails,
                                onIncrementIndent: onIncrementIndent,
                                onDecrementIndent: onDecrementIndent,
                                onOpenChat: onOpenChat,
                                onSelect: onSelect,
                                onHover: onHover,
                                isChatActive: isChatActive,
                                activeChatTaskId: activeChatTaskId,
                                chatCoordinator: chatCoordinator,
                                editingTaskId: editingTaskId,
                                onEditingChanged: onEditingChanged,
                                animateToggleTaskId: animateToggleTaskId
                            )
                            .id(task.id)
                            .modifier(TaskDragDropModifier(
                                isEnabled: !isMultiSelectMode,
                                taskId: task.id,
                                taskDescription: task.description,
                                findTask: { id in orderedTasks.first(where: { $0.id == id }) },
                                findTargetIndex: { orderedTasks.firstIndex(where: { $0.id == task.id }) },
                                validateDrop: { id in orderedTasks.contains(where: { $0.id == id }) },
                                onMoveTask: { droppedTask, targetIndex in
                                    onMoveTask?(droppedTask, targetIndex, category)
                                }
                            ))

                            // Inline creation row after this task
                            if isInlineCreating && inlineCreateAfterTaskId == task.id {
                                InlineTaskCreationRow(
                                    text: $inlineCreateText,
                                    isFocused: $inlineCreateFocused,
                                    onCommit: { _ in onInlineCommit?() },
                                    onCancel: { onInlineCancel?() }
                                )
                                .padding(.top, 4)
                            }
                        }
                    }

                }
            }
        }
    }
}

// MARK: - Conditional Drag & Drop (reduces gesture graph depth when disabled)

/// Conditionally applies .draggable + .dropDestination to avoid deep ExclusiveGesture nesting.
/// When disabled (e.g. multi-select mode), the view has fewer gesture modifiers, preventing hangs.
/// Uses closures instead of the full orderedTasks array to avoid gesture graph rebuilds
/// when the array identity changes during recomputes (every 30s auto-refresh).
struct TaskDragDropModifier: ViewModifier {
    let isEnabled: Bool
    let taskId: String
    let taskDescription: String
    var findTask: ((String) -> TaskActionItem?)?
    var findTargetIndex: (() -> Int?)?
    var validateDrop: ((String) -> Bool)?
    var onMoveTask: ((TaskActionItem, Int) -> Void)?

    func body(content: Content) -> some View {
        if isEnabled {
            content
                .draggable(taskId) {
                    TaskDragPreviewSimple(taskId: taskId, description: taskDescription)
                }
                .dropDestination(for: String.self) { droppedIds, _ in
                    guard let droppedId = droppedIds.first,
                          validateDrop?(droppedId) == true,
                          let targetIndex = findTargetIndex?() else {
                        return false
                    }
                    if let droppedTask = findTask?(droppedId) {
                        onMoveTask?(droppedTask, targetIndex)
                    }
                    return true
                }
        } else {
            content
        }
    }
}

/// Lightweight drag preview that doesn't hold a TaskActionItem reference
struct TaskDragPreviewSimple: View {
    let taskId: String
    let description: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "circle")
                .scaledFont(size: 16)
                .foregroundColor(OmiColors.textTertiary)

            Text(description)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textPrimary)
                .lineLimit(1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.backgroundSecondary)
                .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
        )
        .frame(maxWidth: 300)
    }
}

// MARK: - Chat Session Status Indicator

/// Shows streaming activity or unread dot for a task's chat session.
/// Appears inline in the TaskRow FlowLayout, after AgentStatusIndicator.
struct ChatSessionStatusIndicator: View {
    let task: TaskActionItem
    @ObservedObject var coordinator: TaskChatCoordinator
    var onOpenChat: ((TaskActionItem) -> Void)?

    var body: some View {
        if coordinator.streamingTaskIds.contains(task.id) {
            // Streaming: spinning indicator + status text
            HStack(spacing: 4) {
                ProgressView()
                    .scaleEffect(0.5)
                    .frame(width: 10, height: 10)

                Text(coordinator.streamingStatuses[task.id] ?? "Responding...")
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                    .lineLimit(1)
            }
        } else if coordinator.unreadTaskIds.contains(task.id) {
            // Unread: purple dot
            Button {
                onOpenChat?(task)
            } label: {
                HStack(spacing: 4) {
                    Circle()
                        .fill(OmiColors.purplePrimary)
                        .frame(width: 8, height: 8)

                    Text("New reply")
                        .scaledFont(size: 10, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .buttonStyle(.plain)
            .help("Open chat — new reply available")
        }
    }
}

// MARK: - Task Row

struct TaskRow: View {
    let task: TaskActionItem
    var category: TaskCategory? = nil  // Optional for flat list views

    // Data from ViewModel (passed as values, not via @ObservedObject)
    var indentLevel: Int = 0
    var isMultiSelectMode: Bool = false
    var isSelected: Bool = false
    var isKeyboardSelected: Bool = false

    // Action closures
    var onToggle: ((TaskActionItem) async -> Void)?
    var onDelete: ((TaskActionItem) async -> Void)?
    var onToggleSelection: ((TaskActionItem) -> Void)?
    var onUpdateDetails: ((TaskActionItem, String?, Date?, String?, String?) async -> Void)?
    var onIncrementIndent: ((String) -> Void)?
    var onDecrementIndent: ((String) -> Void)?
    var onOpenChat: ((TaskActionItem) -> Void)?
    var onSelect: ((TaskActionItem) -> Void)?
    var onHover: ((String?) -> Void)?
    var isChatActive: Bool = false
    var activeChatTaskId: String?
    var chatCoordinator: TaskChatCoordinator?

    // Edit mode support (external trigger from keyboard navigation)
    var editingTaskId: String?
    var onEditingChanged: ((Bool) -> Void)?

    // Space-key animated toggle (set by parent when space is pressed)
    var animateToggleTaskId: String?

    @State private var isHovering = false
    @State private var isCompletingAnimation = false
    @State private var checkmarkScale: CGFloat = 1.0
    @State private var rowOpacity: Double = 1.0
    @State private var rowOffset: CGFloat = 0
    @State private var showTaskDetail = false
    @State private var isCopyingLink = false

    // Inline editing state
    @State private var editText = ""
    @FocusState private var isTextFieldFocused: Bool
    @State private var debounceTask: Task<Void, Never>?

    // Inline due date popover
    @State private var showDatePicker = false
    @State private var editDueDate: Date = Date()
    @State private var showRepeatPicker = false
    @State private var editRecurrenceRule: String = ""

    // Swipe gesture state
    @State private var swipeOffset: CGFloat = 0
    @State private var isDragging = false

    /// Threshold for triggering delete (30% of row width, like Flutter)
    private let deleteThreshold: CGFloat = 100
    /// Threshold for triggering indent change (25% of row width)
    private let indentThreshold: CGFloat = 80

    /// Check if task was created less than 1 minute ago (newly added)
    private var isNewlyCreated: Bool {
        Date().timeIntervalSince(task.createdAt) < 60
    }

    /// Indent amount in points (28pt per level, like Flutter)
    private var indentPadding: CGFloat {
        CGFloat(indentLevel) * 28
    }

    /// Whether this task is the one currently shown in the chat sidebar
    private var isActiveChatTask: Bool {
        isChatActive && activeChatTaskId == task.id
    }

    var body: some View {
        swipeableContent
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isActiveChatTask ? OmiColors.purplePrimary.opacity(0.08) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isActiveChatTask ? OmiColors.purplePrimary.opacity(0.3) : Color.clear, lineWidth: 1)
            )
            .contentShape(Rectangle())
            .onTapGesture {
                onSelect?(task)
                if isChatActive, !isActiveChatTask {
                    onOpenChat?(task)
                }
            }
            .sheet(isPresented: $showTaskDetail) {
                TaskDetailView(
                    task: task,
                    onDismiss: { showTaskDetail = false }
                )
            }
    }

    // MARK: - Swipeable Content

    private var swipeableContent: some View {
        ZStack(alignment: .trailing) {
            // Background revealed when swiping left
            if swipeOffset < 0 {
                if indentLevel > 0 {
                    // Indented task: swipe left to outdent
                    outdentBackground
                } else {
                    // Not indented: swipe left to delete
                    deleteBackground
                }
            }

            // Indent background (revealed when swiping right)
            if swipeOffset > 0 && indentLevel < 3 {
                indentBackground
            }

            // Main task row content
            taskRowContent
                .offset(x: swipeOffset)
                .gesture(
                    DragGesture(minimumDistance: 10, coordinateSpace: .local)
                        .onChanged { value in
                            guard !isMultiSelectMode, !isDeletedTask else { return }
                            isDragging = true

                            // Apply resistance at the edges
                            let translation = value.translation.width
                            if translation < 0 {
                                // Swiping left (delete or outdent)
                                swipeOffset = translation * 0.8
                            } else if translation > 0 && indentLevel < 3 {
                                // Swiping right (indent) - only if can indent more
                                swipeOffset = translation * 0.6
                            }
                        }
                        .onEnded { value in
                            isDragging = false
                            handleSwipeEnd(velocity: value.velocity.width)
                        }
                )
        }
        .clipped()
    }

    // MARK: - Swipe Backgrounds

    private var deleteBackground: some View {
        HStack {
            Spacer()
            HStack(spacing: 8) {
                Image(systemName: "trash.fill")
                    .scaledFont(size: 16, weight: .semibold)
                if swipeOffset < -deleteThreshold {
                    Text("Release to delete")
                        .scaledFont(size: 13, weight: .medium)
                }
            }
            .foregroundColor(.white)
            .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.red)
        .cornerRadius(8)
    }

    private var indentBackground: some View {
        HStack {
            HStack(spacing: 8) {
                Image(systemName: "arrow.right.to.line")
                    .scaledFont(size: 16, weight: .semibold)
                if swipeOffset > indentThreshold {
                    Text("Release to indent")
                        .scaledFont(size: 13, weight: .medium)
                }
            }
            .foregroundColor(.white)
            .padding(.horizontal, 20)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.textSecondary)
        .cornerRadius(8)
    }

    /// Outdent background (revealed when swiping left on indented tasks)
    private var outdentBackground: some View {
        HStack {
            Spacer()
            HStack(spacing: 8) {
                if swipeOffset < -indentThreshold {
                    Text("Release to outdent")
                        .scaledFont(size: 13, weight: .medium)
                }
                Image(systemName: "arrow.left.to.line")
                    .scaledFont(size: 16, weight: .semibold)
            }
            .foregroundColor(.white)
            .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.orange)
        .cornerRadius(8)
    }

    // MARK: - Swipe Handling

    private func handleSwipeEnd(velocity: CGFloat) {
        let swipedLeftPastThreshold = swipeOffset < -deleteThreshold || velocity < -500
        let swipedRightPastThreshold = swipeOffset > indentThreshold || velocity > 500

        if swipedLeftPastThreshold {
            if indentLevel > 0 {
                // Outdent (decrease indent) and snap back
                withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                    swipeOffset = 0
                }
                onDecrementIndent?(task.id)
            } else {
                // Delete - animate off screen
                withAnimation(.easeOut(duration: 0.2)) {
                    swipeOffset = -400
                    rowOpacity = 0
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    Task {
                        await onDelete?(task)
                    }
                }
            }
        } else if swipedRightPastThreshold && indentLevel < 3 {
            // Indent (increase indent) and snap back
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                swipeOffset = 0
            }
            onIncrementIndent?(task.id)
        } else {
            // Snap back to original position
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                swipeOffset = 0
            }
        }
    }

    /// Whether this task is soft-deleted
    private var isDeletedTask: Bool {
        task.deleted == true
    }

    private var taskRowContent: some View {
        HStack(alignment: .center, spacing: 12) {
            // Indent visual (vertical line for indented tasks)
            if indentLevel > 0 {
                HStack(spacing: 0) {
                    ForEach(0..<indentLevel, id: \.self) { level in
                        Rectangle()
                            .fill(OmiColors.textQuaternary.opacity(0.5))
                            .frame(width: 2)
                            .padding(.leading, level == 0 ? 8 : 26)
                    }
                }
                .frame(width: indentPadding)
            }

            if isDeletedTask {
                // Deleted tasks: show trash icon instead of checkbox
                Image(systemName: "trash.slash")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
                    .frame(width: 24, height: 24)
            } else if isMultiSelectMode {
                // Multi-select checkbox
                Button {
                    onToggleSelection?(task)
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary, lineWidth: 1.5)
                            .frame(width: 20, height: 20)

                        if isSelected {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(OmiColors.textPrimary)
                                .frame(width: 20, height: 20)

                            Image(systemName: "checkmark")
                                .scaledFont(size: 11, weight: .bold)
                                .foregroundColor(.white)
                        }
                    }
                    .frame(width: 24, height: 24)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                // Completion checkbox with animation
                Button {
                    log("Task: Checkbox clicked for task: \(task.id)")
                    handleToggle()
                } label: {
                    ZStack {
                        Circle()
                            .stroke(isCompletingAnimation || task.completed ? OmiColors.textPrimary : OmiColors.textTertiary, lineWidth: 1.5)
                            .frame(width: 20, height: 20)

                        if isCompletingAnimation || task.completed {
                            Circle()
                                .fill(OmiColors.textPrimary)
                                .frame(width: 20, height: 20)
                                .scaleEffect(checkmarkScale)

                            Image(systemName: "checkmark")
                                .scaledFont(size: 11, weight: .bold)
                                .foregroundColor(.black)
                                .scaleEffect(checkmarkScale)
                        }
                    }
                    .frame(width: 24, height: 24)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }

            // Task content
            if isDeletedTask {
                // Deleted task: strikethrough description + reason
                VStack(alignment: .leading, spacing: 4) {
                    Text(task.description)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                        .strikethrough(true, color: OmiColors.textTertiary)

                    if let reason = task.deletedReason {
                        Text(reason)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textQuaternary)
                            .lineLimit(2)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                // Always-editable task content
                FlowLayout(spacing: 6) {
                    // Always-rendered TextField (notes-like editing)
                    TextField("Task description", text: $editText, axis: .vertical)
                        .textFieldStyle(.plain)
                        .scaledFont(size: 14)
                        .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                        .strikethrough(task.completed, color: OmiColors.textTertiary)
                        .lineLimit(1...4)
                        .focused($isTextFieldFocused)
                        .disabled(isMultiSelectMode)
                        .onKeyPress(.escape) {
                            debounceTask?.cancel()
                            commitEdit()
                            isTextFieldFocused = false
                            return .handled
                        }
                        .onSubmit {
                            debounceTask?.cancel()
                            commitEdit()
                        }
                        .onChange(of: isTextFieldFocused) { _, focused in
                            onEditingChanged?(focused)
                            if !focused {
                                debounceTask?.cancel()
                                commitEdit()
                            }
                        }
                        .onChange(of: editingTaskId) { _, newId in
                            if newId == task.id {
                                isTextFieldFocused = true
                            }
                        }
                        .onChange(of: editText) { _, _ in
                            // Debounced auto-save: save after 1s of no typing
                            debounceTask?.cancel()
                            debounceTask = Task {
                                try? await Task.sleep(nanoseconds: 1_000_000_000)
                                guard !Task.isCancelled else { return }
                                commitEdit()
                            }
                        }
                        .onAppear {
                            editText = task.description
                        }
                        .onChange(of: task.description) { _, newValue in
                            if !isTextFieldFocused {
                                editText = newValue
                            }
                        }

                    // Recurring badge
                    if task.isRecurring {
                        HStack(spacing: 2) {
                            Image(systemName: "repeat")
                                .scaledFont(size: 9)
                        }
                        .foregroundColor(OmiColors.textTertiary)
                    }

                    // New badge
                    if isNewlyCreated {
                        NewBadge()
                    }

                    // Agent status indicator (click status → detail modal, click terminal icon → open terminal)
                    if TaskAgentSettings.shared.isEnabled {
                        AgentStatusIndicator(task: task)
                    }

                    // Chat session status (streaming indicator or unread dot)
                    if let coordinator = chatCoordinator {
                        ChatSessionStatusIndicator(task: task, coordinator: coordinator, onOpenChat: onOpenChat)
                    }

                    // Task detail button (hover for preview, click for full detail)
                    TaskDetailButton(task: task, showDetail: $showTaskDetail)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .popover(isPresented: $showDatePicker) {
                    dueDatePopover
                }
            }

        }
        .overlay(alignment: .trailing) {
            // Hover actions overlaid on trailing edge (no layout shift)
            if isHovering && !isMultiSelectMode && !isDeletedTask {
                HStack(spacing: 4) {
                    // Add date button (shown on hover when no due date)
                    if task.dueAt == nil && !task.completed {
                        Button {
                            editDueDate = Date()
                            showDatePicker = true
                        } label: {
                            Image(systemName: "calendar.badge.plus")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                                .frame(width: 24, height: 24)
                        }
                        .buttonStyle(.plain)
                        .help("Add due date")
                    }

                    // Repeat button
                    if !task.completed {
                        Button {
                            editRecurrenceRule = task.recurrenceRule ?? ""
                            showRepeatPicker = true
                        } label: {
                            Image(systemName: "repeat")
                                .scaledFont(size: 12)
                                .foregroundColor(task.isRecurring ? OmiColors.textPrimary : OmiColors.textTertiary)
                                .frame(width: 24, height: 24)
                        }
                        .buttonStyle(.plain)
                        .help(task.isRecurring ? "Edit repeat" : "Set repeat")
                        .popover(isPresented: $showRepeatPicker) {
                            repeatPopover
                        }
                    }

                    // Outdent button (decrease indent)
                    if indentLevel > 0 {
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                onDecrementIndent?(task.id)
                            }
                        } label: {
                            Image(systemName: "arrow.left.to.line")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                                .frame(width: 24, height: 24)
                        }
                        .buttonStyle(.plain)
                        .help("Decrease indent")
                    }

                    // Indent button (increase indent)
                    if indentLevel < 3 {
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                onIncrementIndent?(task.id)
                            }
                        } label: {
                            Image(systemName: "arrow.right.to.line")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                                .frame(width: 24, height: 24)
                        }
                        .buttonStyle(.plain)
                        .help("Increase indent")
                    }

                    // Share link button
                    Button {
                        Task { await copyShareLink() }
                    } label: {
                        Image(systemName: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .disabled(isCopyingLink)
                    .help("Copy share link")

                    // Delete button
                    Button {
                        Task { await onDelete?(task) }
                    } label: {
                        Image(systemName: "trash")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.trailing, 4)
                .padding(.leading, 8)
                .padding(.vertical, 4)
                .background(
                    HStack(spacing: 0) {
                        LinearGradient(
                            colors: [
                                OmiColors.backgroundTertiary.opacity(0),
                                OmiColors.backgroundTertiary
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                        .frame(width: 24)
                        Rectangle().fill(OmiColors.backgroundTertiary)
                    }
                )
                .transition(.opacity)
            }
        }
        .padding(.leading, indentPadding > 0 ? 0 : 12)
        .padding(.trailing, 12)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isKeyboardSelected ? OmiColors.purplePrimary.opacity(0.10) : (isHovering || isDragging ? OmiColors.backgroundTertiary : (isNewlyCreated ? OmiColors.purplePrimary.opacity(0.15) : Color.clear)))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isKeyboardSelected ? OmiColors.purplePrimary.opacity(0.3) : Color.clear, lineWidth: 1)
        )
        .overlay(alignment: .leading) {
            if isKeyboardSelected {
                RoundedRectangle(cornerRadius: 2)
                    .fill(OmiColors.purplePrimary)
                    .frame(width: 3)
                    .padding(.vertical, 4)
            }
        }
        .opacity(rowOpacity)
        .offset(x: rowOffset)
        .onAppear {
            rowOpacity = 1.0
            rowOffset = 0
            isCompletingAnimation = false
            checkmarkScale = 1.0
        }
        .onChange(of: task.completed) { _, _ in
            rowOpacity = 1.0
            rowOffset = 0
            isCompletingAnimation = false
            checkmarkScale = 1.0
        }
        .onChange(of: animateToggleTaskId) { _, newValue in
            if newValue == task.id {
                handleToggle()
            }
        }
        .onHover { hovering in
            isHovering = hovering
            onHover?(hovering ? task.id : nil)
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
    }

    // MARK: - Inline Editing

    private func commitEdit() {
        let trimmed = editText.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmed.isEmpty, trimmed != task.description else {
            // Reset to original if empty or unchanged
            editText = task.description
            return
        }

        Task {
            await onUpdateDetails?(task, trimmed, nil, nil, nil)
        }
    }

    // MARK: - Share Link

    private func copyShareLink() async {
        guard !isCopyingLink else { return }
        isCopyingLink = true
        defer { isCopyingLink = false }

        do {
            let response = try await APIClient.shared.shareTasks(taskIds: [task.id])
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(response.url, forType: .string)
            log("Copied task share link to clipboard: \(response.url)")
        } catch {
            log("Failed to get task share link: \(error)")
        }
    }

    // MARK: - Due Date Popover

    private var dueDatePopover: some View {
        VStack(spacing: 12) {
            DatePicker(
                "Due Date",
                selection: $editDueDate,
                displayedComponents: [.date, .hourAndMinute]
            )
            .datePickerStyle(.graphical)
            .labelsHidden()

            HStack(spacing: 8) {
                Button("Cancel") {
                    showDatePicker = false
                }
                .buttonStyle(.bordered)

                Button("Save") {
                    showDatePicker = false
                    Task {
                        await onUpdateDetails?(task, nil, editDueDate, nil, nil)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(OmiColors.textPrimary)
            }
        }
        .padding(16)
        .frame(width: 300)
    }

    private var repeatPopover: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Repeat")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
            }

            Picker("", selection: $editRecurrenceRule) {
                Text("Never").tag("")
                Text("Daily").tag("daily")
                Text("Weekdays").tag("weekdays")
                Text("Weekly").tag("weekly")
                Text("Every 2 Weeks").tag("biweekly")
                Text("Monthly").tag("monthly")
            }
            .pickerStyle(.radioGroup)

            HStack(spacing: 8) {
                Button("Cancel") {
                    showRepeatPicker = false
                }
                .buttonStyle(.bordered)

                Button("Save") {
                    showRepeatPicker = false
                    let ruleToSave = editRecurrenceRule.isEmpty ? "" : editRecurrenceRule
                    Task {
                        await onUpdateDetails?(task, nil, nil, nil, ruleToSave)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(OmiColors.textPrimary)
            }
        }
        .padding(16)
        .frame(width: 200)
    }

    private func handleToggle() {
        log("Task: handleToggle called, completed=\(task.completed)")

        if task.completed {
            log("Task: Already completed, toggling back")
            Task {
                await onToggle?(task)
            }
            return
        }

        log("Task: Starting completion animation")
        isCompletingAnimation = true

        withAnimation(.spring(response: 0.3, dampingFraction: 0.5)) {
            checkmarkScale = 1.2
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            withAnimation(.spring(response: 0.2, dampingFraction: 0.7)) {
                self.checkmarkScale = 1.0
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            withAnimation(.easeInOut(duration: 0.3)) {
                self.rowOpacity = 0.0
                self.rowOffset = 50
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
            log("Task: Animation complete, calling toggleTask")
            Task {
                await self.onToggle?(self.task)
            }
        }
    }
}

// FlowLayout is defined in AppsPage.swift

// MARK: - Interactive Badges

struct DueDateBadgeInteractive: View {
    let dueAt: Date
    let isCompleted: Bool
    let isRecurring: Bool
    @Binding var showDatePicker: Bool
    @Binding var editDueDate: Date

    @State private var isHovering = false

    private var displayText: String {
        let calendar = Calendar.current
        let now = Date()
        let startOfToday = calendar.startOfDay(for: now)
        let startOfTomorrow = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
        let startOfDayAfterTomorrow = calendar.date(byAdding: .day, value: 2, to: startOfToday)!
        let endOfWeek = calendar.date(byAdding: .day, value: 7, to: startOfToday)!

        if isCompleted {
            return dueAt.formatted(date: .abbreviated, time: .omitted)
        }

        if dueAt < startOfToday {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .short
            return formatter.localizedString(for: dueAt, relativeTo: now)
        } else if dueAt < startOfTomorrow {
            return "Today"
        } else if dueAt < startOfDayAfterTomorrow {
            return "Tomorrow"
        } else if dueAt < endOfWeek {
            return calendar.weekdaySymbols[calendar.component(.weekday, from: dueAt) - 1]
        } else {
            return dueAt.formatted(date: .abbreviated, time: .omitted)
        }
    }

    var body: some View {
        Button {
            editDueDate = dueAt
            showDatePicker = true
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "calendar")
                    .scaledFont(size: 9)
                Text(displayText)
                    .scaledFont(size: 11, weight: .medium)
                if isRecurring {
                    Image(systemName: "repeat")
                        .scaledFont(size: 9)
                }
                if isHovering {
                    Image(systemName: "pencil")
                        .scaledFont(size: 8)
                }
            }
            .foregroundColor(isHovering ? OmiColors.textPrimary : OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
        }
    }
}

struct PriorityBadgeInteractive: View {
    let priority: String?
    let isCompleted: Bool
    let isHovering: Bool  // Row hover state
    @Binding var showPriorityPicker: Bool
    let onPriorityChange: (String) -> Void

    @State private var badgeHovering = false

    private var badgeColor: Color {
        switch priority {
        case "high": return OmiColors.textPrimary
        case "medium": return OmiColors.textSecondary
        case "low": return OmiColors.textTertiary
        default: return OmiColors.textTertiary
        }
    }

    private var label: String {
        priority?.capitalized ?? "Priority"
    }

    var body: some View {
        // Show if task has a priority, or show "add priority" on hover
        if priority != nil || (isHovering && !isCompleted) {
            Button {
                showPriorityPicker = true
            } label: {
                HStack(spacing: 3) {
                    if priority != nil {
                        Image(systemName: priority == "high" ? "flag.fill" : "flag")
                            .scaledFont(size: 8)
                    } else {
                        Image(systemName: "plus")
                            .scaledFont(size: 8)
                    }
                    Text(label)
                        .scaledFont(size: 10, weight: .medium)
                    if badgeHovering && priority != nil {
                        Image(systemName: "pencil")
                            .scaledFont(size: 7)
                    }
                }
                .foregroundColor(badgeHovering ? badgeColor : (priority != nil ? OmiColors.textSecondary : OmiColors.textTertiary))
            }
            .buttonStyle(.plain)
            .onHover { hovering in
                badgeHovering = hovering
            }
            .popover(isPresented: $showPriorityPicker) {
                VStack(spacing: 4) {
                    ForEach(["high", "medium", "low"], id: \.self) { value in
                        let color: Color = value == "high" ? OmiColors.textPrimary : value == "medium" ? OmiColors.textSecondary : OmiColors.textTertiary
                        let isSelected = priority == value

                        Button {
                            showPriorityPicker = false
                            onPriorityChange(value)
                        } label: {
                            HStack {
                                Image(systemName: value == "high" ? "flag.fill" : "flag")
                                    .scaledFont(size: 12)
                                    .foregroundColor(color)
                                    .frame(width: 20)
                                Text(value.capitalized)
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textPrimary)
                                Spacer()
                                if isSelected {
                                    Image(systemName: "checkmark")
                                        .scaledFont(size: 12, weight: .medium)
                                        .foregroundColor(color)
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(isSelected ? color.opacity(0.1) : Color.clear)
                            .cornerRadius(6)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(8)
                .frame(width: 180)
            }
        }
    }
}

struct SourceBadgeCompact: View {
    let source: String
    let sourceLabel: String
    let sourceIcon: String
    var windowTitle: String? = nil

    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: sourceIcon)
                .scaledFont(size: 8)
            Text(sourceLabel)
                .scaledFont(size: 10, weight: .medium)
        }
        .foregroundColor(OmiColors.textSecondary)
        .help(windowTitle ?? sourceLabel)
    }
}


// MARK: - New Badge

struct NewBadge: View {
    var body: some View {
        Text("New")
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(OmiColors.purplePrimary.opacity(0.15))
            .cornerRadius(4)
    }
}

// MARK: - Task Create Sheet

struct TaskCreateSheet: View {
    @ObservedObject var viewModel: TasksViewModel
    var onDismiss: (() -> Void)? = nil

    @State private var description: String = ""
    @State private var hasDueDate: Bool = false
    @State private var dueDate: Date = Date()
    @State private var priority: String? = nil
    @State private var selectedTags: Set<String> = []
    @State private var isSaving = false

    @Environment(\.dismiss) private var environmentDismiss

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    private var canSave: Bool {
        !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("New Task")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: dismissSheet)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)

            Divider()
                .background(OmiColors.border)

            // Content
            ScrollView {
                VStack(spacing: 20) {
                    // Description field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Description")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)

                        TextField("What needs to be done?", text: $description, axis: .vertical)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 14)
                            .lineLimit(3...6)
                            .padding(12)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.backgroundSecondary)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(OmiColors.border, lineWidth: 1)
                            )
                    }

                    // Due date
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Due Date")
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                            Toggle("", isOn: $hasDueDate)
                                .toggleStyle(.switch)
                                .labelsHidden()
                                .controlSize(.small)
                        }
                        if hasDueDate {
                            DatePicker("", selection: $dueDate, displayedComponents: [.date, .hourAndMinute])
                                .datePickerStyle(.graphical)
                                .labelsHidden()
                                .padding(12)
                                .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.backgroundSecondary))
                        }
                    }

                    // Priority
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Priority")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                        HStack(spacing: 8) {
                            createPriorityButton(label: "None", value: nil)
                            createPriorityButton(label: "Low", value: "low", color: OmiColors.textTertiary)
                            createPriorityButton(label: "Medium", value: "medium", color: OmiColors.textSecondary)
                            createPriorityButton(label: "High", value: "high", color: OmiColors.textPrimary)
                        }
                    }

                    // Tags
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Tags")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)

                        // Flow layout of toggleable tag pills
                        let allTags = TaskClassification.allCases
                        LazyVGrid(columns: [
                            GridItem(.adaptive(minimum: 90), spacing: 6)
                        ], spacing: 6) {
                            ForEach(allTags, id: \.rawValue) { classification in
                                let isSelected = selectedTags.contains(classification.rawValue)
                                let tagColor = Color(hex: classification.color) ?? OmiColors.textSecondary
                                Button {
                                    if isSelected {
                                        selectedTags.remove(classification.rawValue)
                                    } else {
                                        selectedTags.insert(classification.rawValue)
                                    }
                                } label: {
                                    HStack(spacing: 3) {
                                        Image(systemName: classification.icon)
                                            .scaledFont(size: 9)
                                        Text(classification.label)
                                            .scaledFont(size: 12, weight: isSelected ? .semibold : .medium)
                                    }
                                    .foregroundColor(isSelected ? .white : tagColor)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 6)
                                    .background(
                                        Capsule()
                                            .fill(isSelected ? tagColor : tagColor.opacity(0.1))
                                    )
                                    .overlay(
                                        Capsule()
                                            .stroke(isSelected ? Color.clear : tagColor.opacity(0.3), lineWidth: 1)
                                    )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(20)
            }

            Divider()
                .background(OmiColors.border)

            // Footer
            HStack(spacing: 12) {
                Button("Cancel") { dismissSheet() }
                    .buttonStyle(.bordered)
                    .controlSize(.large)

                Button {
                    Task { await createTask() }
                } label: {
                    if isSaving {
                        ProgressView().controlSize(.small).frame(width: 60)
                    } else {
                        Text("Create").frame(width: 60)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(OmiColors.textPrimary)
                .controlSize(.large)
                .disabled(!canSave || isSaving)
            }
            .padding(20)
        }
        .frame(width: 420, height: 500)
        .background(OmiColors.backgroundPrimary)
    }

    private func createPriorityButton(label: String, value: String?, color: Color = OmiColors.textSecondary) -> some View {
        let isSelected = priority == value
        return Button {
            priority = value
        } label: {
            Text(label)
                .scaledFont(size: 13, weight: isSelected ? .semibold : .medium)
                .foregroundColor(isSelected ? OmiColors.backgroundPrimary : color)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isSelected ? (value != nil ? color : OmiColors.textSecondary) : Color.clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? Color.clear : OmiColors.border, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }

    private func createTask() async {
        let trimmed = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSaving = true
        let tags = selectedTags.isEmpty ? nil : Array(selectedTags)
        await viewModel.createTask(description: trimmed, dueAt: hasDueDate ? dueDate : nil, priority: priority, tags: tags)
        isSaving = false
        dismissSheet()
    }
}

// MARK: - Undo Toast View

struct UndoToastView: View {
    let taskDescription: String
    let undoCount: Int
    let onUndo: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "trash")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.white.opacity(0.7))

            Text("Task deleted")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.white)
                .lineLimit(1)

            if undoCount > 1 {
                Text("(\(undoCount))")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.white.opacity(0.5))
            }

            Spacer()

            Button {
                onUndo()
            } label: {
                Text("Undo")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(.white.opacity(0.2))
                    )
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            Capsule()
                .fill(Color(.darkGray))
                .shadow(color: .black.opacity(0.3), radius: 8, x: 0, y: 4)
        )
        .frame(maxWidth: 360)
    }
}

// MARK: - Inline Task Creation Row

struct InlineTaskCreationRow: View {
    @Binding var text: String
    @FocusState.Binding var isFocused: Bool
    let onCommit: (String) -> Void
    let onCancel: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            // Circle placeholder (matches TaskRow checkbox)
            Circle()
                .stroke(OmiColors.purplePrimary.opacity(0.5), lineWidth: 1.5)
                .frame(width: 20, height: 20)
                .padding(.leading, 12)

            TextField("New task...", text: $text)
                .textFieldStyle(.plain)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .focused($isFocused)
                .onSubmit {
                    onCommit(text)
                }
                .onKeyPress(.escape) {
                    onCancel()
                    return .handled
                }

            Spacer()
        }
        .padding(.trailing, 12)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.purplePrimary.opacity(0.05))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(OmiColors.purplePrimary.opacity(0.3), lineWidth: 1)
        )
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2)
                .fill(OmiColors.purplePrimary)
                .frame(width: 3)
                .padding(.vertical, 4)
        }
    }
}

// MARK: - Keyboard Hint Bar

struct KeyboardHintBar: View {
    let isAnyTaskEditing: Bool
    let isInlineCreating: Bool
    let hasSelection: Bool

    var body: some View {
        HStack(spacing: 16) {
            if isInlineCreating {
                keyboardHint("\u{21A9}", label: "Create")
                keyboardHint("esc", label: "Cancel")
            } else if isAnyTaskEditing {
                keyboardHint("esc", label: "Save & exit")
            } else if hasSelection {
                keyboardHint("\u{2191} \u{2193}", label: "Navigate")
                keyboardHint("\u{21A9}", label: "New below")
                keyboardHint("\u{21A9} \u{21A9}", label: "Edit")
                keyboardHint("\u{2423}", label: "Done")
                keyboardHint("esc", label: "Deselect")
                keyboardHint("\u{2318}D", label: "Delete")
                keyboardHint("\u{21E5}", label: "Indent")
                keyboardHint("\u{21E7} \u{21E5}", label: "Outdent")
            } else {
                keyboardHint("\u{2191} \u{2193}", label: "Navigate")
                keyboardHint("\u{2318}N", label: "New")
                keyboardHint("\u{2318}D", label: "Delete")
                keyboardHint("\u{21E5}", label: "Indent")
                keyboardHint("\u{21E7} \u{21E5}", label: "Outdent")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(
            Capsule()
                .fill(OmiColors.backgroundSecondary)
                .shadow(color: .black.opacity(0.15), radius: 4, x: 0, y: 2)
        )
    }

    private func keyboardHint(_ key: String, label: String) -> some View {
        HStack(spacing: 6) {
            Text(key)
                .scaledFont(size: 11, weight: .medium, design: .monospaced)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 7)
                .padding(.vertical, 4)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(4)

            Text(label)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
        }
    }
}
