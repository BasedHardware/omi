func index(_ records: [(String, Int)]) -> [String: Int] {
  Dictionary(lastWriteWins: records)
}

func staticIndex() -> [String: Int] {
  // omi-collection-safety: static-unique-keys -- enum raw values are unique by construction
  Dictionary(uniqueKeysWithValues: [("one", 1), ("two", 2)])
}
