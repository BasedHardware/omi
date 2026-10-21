/// Sentinel: proves `BareSlashRegexLiterals` is active by using a bare-slash
/// regex literal.  If the feature is removed or misspelled in Package.swift,
/// this file fails to compile — the regex literal is a syntax error without it.
func semanticBareSlashRegexSentinel(_ input: String) throws -> Bool {
  let pattern = /\d+/
  return try pattern.wholeMatch(in: input) != nil
}
