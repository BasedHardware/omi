extension Dictionary {
  /// Builds a dictionary without trapping when a sequence contains duplicate keys.
  ///
  /// Values are applied in sequence order, so the final value for a key is the
  /// last one in the input. Prefer this initializer for API responses, decoded
  /// persistence, projections, and other data whose uniqueness is not enforced
  /// by the Swift type system.
  public init<S: Sequence>(lastWriteWins pairs: S) where S.Element == (Key, Value) {
    self.init()
    for (key, value) in pairs {
      self[key] = value
    }
  }
}
