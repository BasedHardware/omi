func staticIndex() -> [String: Int] {
  // omi-collection-safety: static-unique-keys
  Dictionary(uniqueKeysWithValues: [("one", 1)])
}
