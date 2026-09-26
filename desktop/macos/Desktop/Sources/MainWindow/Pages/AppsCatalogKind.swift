/// The Apps surface contains three different catalog kinds. Keeping the kind
/// explicit prevents marketplace filters from looking like they also refine
/// local imports and memory exports.
enum AppsCatalogKind: String, CaseIterable, Identifiable {
  case all = "All"
  case apps = "Apps"
  case imports = "Imports"
  case exports = "Exports"

  var id: String { rawValue }

  var icon: String {
    switch self {
    case .all: return "square.grid.2x2"
    case .apps: return "app.badge"
    case .imports: return "arrow.down.circle"
    case .exports: return "arrow.up.circle"
    }
  }

  func searchResultCount(apps: Int, imports: Int, exports: Int) -> Int {
    switch self {
    case .all: apps + imports + exports
    case .apps: apps
    case .imports: imports
    case .exports: exports
    }
  }
}
