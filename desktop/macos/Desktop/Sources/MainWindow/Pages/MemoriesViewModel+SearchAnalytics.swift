import Foundation

extension MemoriesViewModel {
  func openMemoryFromSearch(_ memory: ServerMemory) {
    SearchAnalytics.resultOpened(
      surface: .memories,
      resultIndex: filteredMemories.firstIndex { $0.id == memory.id },
      searchIsActive: DebouncedSearchCoordinator.isActive(searchText))
    selectedMemory = memory
  }
}
