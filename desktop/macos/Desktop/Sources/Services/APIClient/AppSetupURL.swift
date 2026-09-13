import Foundation

/// `uid` hand-off for external-integration setup URLs.
///
/// `authSteps[].url` and `setupCompletedUrl` come from third-party app
/// manifests and may already carry their own query (`?state=...`) or a
/// fragment. Naively concatenating `"?uid=\(uid)"` onto such a URL produces
/// `https://x/setup?a=b?uid=u`, where `uid` lands inside another parameter's
/// value and the provider never sees it — so the browser opens an
/// unattributed setup page and `isAppSetupCompleted` polls a URL that can
/// never report completion.
///
/// The uid item is appended to the raw `percentEncodedQuery` bytes rather
/// than through `queryItems`: reading `queryItems` decodes and re-encodes the
/// existing query, which can rewrite percent-encoded characters a provider
/// signature depends on. Any `uid` the base already carries is dropped so the
/// handed-off value is unambiguous.
enum AppSetupURL {
  static func withUID(_ base: String, uid: String) -> URL? {
    guard !base.isEmpty, var components = URLComponents(string: base) else { return nil }
    var uidComponents = URLComponents()
    uidComponents.queryItems = [URLQueryItem(name: "uid", value: uid)]
    guard let encodedUID = uidComponents.percentEncodedQuery else { return nil }
    let preserved =
      (components.percentEncodedQuery ?? "")
      .split(separator: "&")
      .map(String.init)
      .filter { $0.split(separator: "=", maxSplits: 1).first != "uid" }
    components.percentEncodedQuery = (preserved + [encodedUID]).joined(separator: "&")
    return components.url
  }
}
