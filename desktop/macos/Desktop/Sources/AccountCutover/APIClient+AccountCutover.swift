import Foundation

extension APIClient {
  func getAccountCutoverControl() async throws -> AccountCutoverControl {
    try await get("v1/account/cutover/control")
  }
}
