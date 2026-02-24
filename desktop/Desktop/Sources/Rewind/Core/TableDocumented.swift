/// Conforming GRDB record types must declare human-readable descriptions
/// for use in LLM system prompts and developer documentation.
protocol TableDocumented {
    static var tableDescription: String { get }
    static var columnDescriptions: [String: String] { get }
}
