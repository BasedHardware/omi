func index(_ records: [(String, Int)]) -> [String: Int] {
  let result: Dictionary<String, Int> = .init(uniqueKeysWithValues: records)
  return result
}
