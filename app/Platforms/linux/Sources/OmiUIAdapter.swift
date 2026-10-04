// SwiftPM entry for the OmiUI → OpenSwiftUI adapter seam (Linux/Windows
// desktop hosts). Apple SwiftUI view trees (`OmiUI.RootView`) and OpenSwiftUI
// view trees are distinct type systems today; this file documents the seam
// rather than shipping a fake bridge. Decision for the user: EITHER
//   (a) compile OmiUI itself against OpenSwiftUI on non-Apple platforms via a
//       conditional-import shim module (`@_exported`-style typealias layer:
//       View/Text/VStack/… → OpenSwiftUI), requiring upstream API coverage
//       (windowing, text layout, materials, transitions) that does not exist
//       yet on Linux (stdout renderer only) or Windows (unsupported), OR
//   (b) fork/own an adapter that re-expresses the Desktop surface in
//       OpenSwiftUI terms.
// Until one lands, `OmiOpenSwiftUIShell.swift` carries the only
// OpenSwiftUI-conforming code in this host.
