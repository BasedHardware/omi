import Foundation

// Port of `react-native/src/desktopCloudClient.ts` — Settings/Connectors
// reads and writes over the authenticated transport.

public enum CloudClientError: Error, Sendable, Equatable {
    case unauthorized
    case failed(id: String, status: Int)
    case serviceUnavailable
    case malformed(String)
    case appIDMalformed
}

func cloudRequest(
    _ transport: BackendTransport, id: String, method: HTTPMethod, path: String
) async throws -> (status: Int, body: JSONValue) {
    let response = try await transport.request(
        BackendRequest(id: id, method: method, path: path))
    if response.status == 401 { throw CloudClientError.unauthorized }
    if response.status != 200 {
        if response.status == 503, let body = response.body,
            JSON.parseOrNull(body)?["error"]?.stringValue == "service_unavailable"
        {
            throw CloudClientError.serviceUnavailable
        }
        throw CloudClientError.failed(id: id, status: response.status)
    }
    guard let body = response.body else {
        throw CloudClientError.malformed("\(id) returned an empty response")
    }
    guard let parsed = JSON.parseOrNull(body) else {
        throw CloudClientError.malformed("\(id) returned invalid JSON")
    }
    return (response.status, parsed)
}

func optionalString(_ value: JSONValue?) -> String? {
    if let text = value?.stringValue, !text.isEmpty { return text }
    return nil
}

func optionalBoolean(_ value: JSONValue?) -> Bool? {
    value?.boolValue
}

func optionalInteger(_ value: JSONValue?) -> Int64? {
    value?.safeIntegerValue
}

/// Port of `parseCloudApp`. Deleted rows throw; `parseCloudApps` drops them.
public func parseCloudApp(_ value: JSONValue?, _ label: String) throws -> CloudApp {
    guard let record = value, record.isRecord else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    guard let id = optionalString(record["id"]), let name = optionalString(record["name"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    if record["deleted"]?.boolValue == true {
        throw CloudClientError.malformed("\(label) is deleted")
    }
    if record["connected_accounts"]?.arrayValue != nil {
        guard record["connected_accounts"]!.arrayValue!.allSatisfy({ $0.stringValue != nil })
        else {
            throw CloudClientError.malformed("\(label) connected_accounts are malformed")
        }
    }
    return CloudApp(
        id: id, name: name,
        description: record["description"]?.stringValue ?? "",
        category: record["category"]?.stringValue ?? "",
        author: record["author"]?.stringValue ?? "",
        enabled: record["enabled"]?.boolValue == true,
        uid: optionalString(record["uid"]),
        isPrivate: record["private"]?.boolValue == true,
        official: record["official"]?.boolValue == true,
        installs: Int(optionalInteger(record["installs"]) ?? 0),
        hasExternalIntegration: !isNullValue(record["external_integration"]),
        connectedAccounts: record["connected_accounts"]?.arrayValue?.compactMap {
            $0.stringValue
        } ?? []
    )
}

public func parseCloudApps(_ value: JSONValue?, _ label: String) throws -> [CloudApp] {
    guard let array = value?.arrayValue else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    var apps = [CloudApp]()
    for (index, entry) in array.enumerated() {
        do {
            apps.append(try parseCloudApp(entry, "\(label) item \(index)"))
        } catch let error as CloudClientError {
            guard case .malformed(let message) = error,
                message == "\(label) item \(index) is deleted"
            else { throw error }
        }
    }
    return apps
}

public func parseEnabledAppIds(_ value: JSONValue?, _ label: String) throws -> [String] {
    guard let array = value?.arrayValue, array.allSatisfy({ $0.stringValue != nil }) else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return array.compactMap { $0.stringValue }
}

public func parseCloudProfile(_ value: JSONValue?, _ label: String) throws -> CloudProfile {
    guard let record = value, record.isRecord, let uid = optionalString(record["uid"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return CloudProfile(
        uid: uid, name: optionalString(record["name"]),
        email: optionalString(record["email"]),
        company: optionalString(record["company"]), job: optionalString(record["job"]),
        dataProtectionLevel: optionalString(record["data_protection_level"]))
}

public func parseCloudSubscription(
    _ value: JSONValue?, _ label: String
) throws -> CloudSubscription {
    guard let record = value, record.isRecord else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    let subscriptionRecord = record["subscription"]
    let subscription: JSONValue
    if isNullValue(subscriptionRecord) || subscriptionRecord == nil {
        subscription = record
    } else {
        guard let inner = subscriptionRecord, inner.isRecord else {
            throw CloudClientError.malformed("\(label) subscription is malformed")
        }
        subscription = inner
    }
    guard let plan = optionalString(subscription["plan"]),
        let status = optionalString(subscription["status"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return CloudSubscription(
        plan: plan, status: status,
        transcriptionSecondsUsed: optionalInteger(record["transcription_seconds_used"])
            .map(Int.init),
        transcriptionSecondsLimit: optionalInteger(record["transcription_seconds_limit"])
            .map(Int.init))
}

public func parseStoreRecordingPermission(
    _ value: JSONValue?, _ label: String
) throws -> Bool {
    guard let record = value, record.isRecord,
        let permission = optionalBoolean(record["store_recording_permission"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return permission
}

public func parseTrainingOptIn(_ value: JSONValue?, _ label: String) throws -> Bool {
    guard let record = value, record.isRecord,
        let optedIn = optionalBoolean(record["opted_in"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return optedIn
}

public func parsePrivateCloudSync(_ value: JSONValue?, _ label: String) throws -> Bool {
    guard let record = value, record.isRecord,
        let enabled = optionalBoolean(record["private_cloud_sync_enabled"])
    else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return enabled
}

public func parseWebhookStatuses(
    _ value: JSONValue?, _ label: String
) throws -> [CloudWebhookStatus] {
    guard let record = value, record.isRecord else {
        throw CloudClientError.malformed("\(label) is malformed")
    }
    return try (record.objectValue ?? []).map { type, entry in
        if let flag = entry.boolValue {
            return CloudWebhookStatus(type: type, enabled: flag, url: nil)
        }
        guard entry.isRecord else {
            throw CloudClientError.malformed("\(label) \(type) is malformed")
        }
        return CloudWebhookStatus(
            type: type,
            enabled: entry["enabled"] != nil ? optionalBoolean(entry["enabled"])
                : optionalBoolean(entry["status"]),
            url: optionalString(entry["url"]))
    }
}

func settledError(_ error: Error) -> String {
    desktopReadErrorCopy(error)
}

func readOptional<Value>(
    _ load: () async throws -> Value
) async -> (value: Value?, error: String?) {
    do {
        return (try await load(), nil)
    } catch {
        return (nil, settledError(error))
    }
}

public func loadConnectors(
    _ transport: BackendTransport
) async throws -> ConnectorsSnapshot {
    let appsResult = await readOptional {
        try parseCloudApps(
            try await cloudRequest(transport, id: "desktop-apps-read", method: .GET, path: "/v1/apps")
                .body,
            "Apps response")
    }
    guard let apps = appsResult.value else { throw CloudClientError.malformed(appsResult.error ?? "") }
    let owner = await readOptional {
        try parseCloudProfile(
            try await cloudRequest(
                transport, id: "desktop-connectors-profile", method: .GET,
                path: "/v1/users/profile"
            ).body,
            "Profile response")
    }
    let enabledResult = await readOptional {
        try parseEnabledAppIds(
            try await cloudRequest(
                transport, id: "desktop-apps-enabled", method: .GET,
                path: "/v1/apps/enabled"
            ).body,
            "Enabled apps response")
    }
    guard let enabledIds = enabledResult.value else {
        return ConnectorsSnapshot(
            apps: apps, enabledIds: nil, enabledError: enabledResult.error,
            ownerUid: owner.value?.uid)
    }
    let enabled = Set(enabledIds)
    return ConnectorsSnapshot(
        apps: apps.map { app in
            var app = app
            app.enabled = app.enabled || enabled.contains(app.id)
            return app
        },
        enabledIds: enabledIds, enabledError: nil, ownerUid: owner.value?.uid)
}

public func loadAccountSettings(
    _ transport: BackendTransport
) async -> AccountSettingsSnapshot {
    let profile = await readOptional {
        try parseCloudProfile(
            try await cloudRequest(
                transport, id: "desktop-profile-read", method: .GET,
                path: "/v1/users/profile"
            ).body,
            "Profile response")
    }
    let subscription = await readOptional {
        try parseCloudSubscription(
            try await cloudRequest(
                transport, id: "desktop-subscription-read", method: .GET,
                path: "/v1/users/me/subscription"
            ).body,
            "Subscription response")
    }
    let recording = await readOptional {
        try parseStoreRecordingPermission(
            try await cloudRequest(
                transport, id: "desktop-recording-permission-read", method: .GET,
                path: "/v1/users/store-recording-permission"
            ).body,
            "Recording permission response")
    }
    let training = await readOptional {
        try parseTrainingOptIn(
            try await cloudRequest(
                transport, id: "desktop-training-opt-in-read", method: .GET,
                path: "/v1/users/training-data-opt-in"
            ).body,
            "Training opt-in response")
    }
    let privateCloudSync = await readOptional {
        try parsePrivateCloudSync(
            try await cloudRequest(
                transport, id: "desktop-private-cloud-sync-read", method: .GET,
                path: "/v1/users/private-cloud-sync"
            ).body,
            "Private cloud sync response")
    }
    let webhooks = await readOptional {
        try parseWebhookStatuses(
            try await cloudRequest(
                transport, id: "desktop-webhooks-read", method: .GET,
                path: "/v1/users/developer/webhooks/status"
            ).body,
            "Webhooks response")
    }
    return AccountSettingsSnapshot(
        profile: profile.value, profileError: profile.error,
        subscription: subscription.value, subscriptionError: subscription.error,
        storeRecordingPermission: recording.value,
        storeRecordingError: recording.error, trainingOptedIn: training.value,
        trainingError: training.error, privateCloudSync: privateCloudSync.value,
        privateCloudSyncError: privateCloudSync.error,
        webhooks: webhooks.value, webhooksError: webhooks.error)
}

func expectOk(
    _ transport: BackendTransport, id: String, path: String
) async throws {
    let result = try await cloudRequest(transport, id: id, method: .POST, path: path)
    guard result.body.isRecord, result.body["status"]?.stringValue == "ok" else {
        throw CloudClientError.malformed("\(id) failed")
    }
}

public func enableCloudApp(
    _ transport: BackendTransport, appId: String
) async throws {
    guard !appId.isEmpty else { throw CloudClientError.appIDMalformed }
    try await expectOk(
        transport, id: "desktop-app-enable",
        path: "/v1/apps/enable?app_id=\(encodeQueryComponent(appId))")
}

public func disableCloudApp(
    _ transport: BackendTransport, appId: String
) async throws {
    guard !appId.isEmpty else { throw CloudClientError.appIDMalformed }
    try await expectOk(
        transport, id: "desktop-app-disable",
        path: "/v1/apps/disable?app_id=\(encodeQueryComponent(appId))")
}

public func setStoreRecordingPermission(
    _ transport: BackendTransport, value: Bool
) async throws {
    try await expectOk(
        transport, id: "desktop-recording-permission-write",
        path: "/v1/users/store-recording-permission?value=\(value)")
}

public func setPrivateCloudSync(
    _ transport: BackendTransport, value: Bool
) async throws {
    try await expectOk(
        transport, id: "desktop-private-cloud-sync-write",
        path: "/v1/users/private-cloud-sync?value=\(value)")
}

public func optInTrainingData(_ transport: BackendTransport) async throws {
    try await expectOk(
        transport, id: "desktop-training-opt-in-write",
        path: "/v1/users/training-data-opt-in")
}

public func cloudSessionUnavailableCopy(_ transport: BackendTransport?) -> String {
    transport == nil ? desktopBackendConfigurationCopy : desktopBackendUnauthorizedCopy
}

public func exploreApps(_ snapshot: ConnectorsSnapshot) -> [CloudApp] { snapshot.apps }

public func installedApps(_ snapshot: ConnectorsSnapshot) -> [CloudApp] {
    snapshot.apps.filter { $0.enabled }
}

public func myApps(_ snapshot: ConnectorsSnapshot, uid: String?) -> [CloudApp] {
    guard let uid else { return [] }
    return snapshot.apps.filter { $0.uid == uid }
}

public func serviceApps(_ snapshot: ConnectorsSnapshot) -> [CloudApp] {
    snapshot.apps.filter { $0.hasExternalIntegration || !$0.connectedAccounts.isEmpty }
}

// MARK: - Service settings

public struct ServiceIdentity: Sendable, Equatable {
    public var displayName: String
    public var email: String
}

public struct ServiceEntitlement: Sendable, Equatable {
    public var limitKey: String
    public var used: Double
    public var limit: Double?
}

public struct ServiceSettingsSnapshot: Sendable, Equatable {
    public var identity: ServiceIdentity?
    public var entitlement: ServiceEntitlement?
}

public func loadServiceSettings(
    _ transport: BackendTransport
) async throws -> ServiceSettingsSnapshot {
    let response = try await cloudRequest(
        transport, id: "service-settings-read", method: .GET, path: "/v1/settings")
    let body: JSONValue
    do {
        let parsed = response.body
        if parsed.isRecord {
            body = parsed
        } else {
            throw CloudClientError.malformed("Settings response is malformed")
        }
    }
    var identity: ServiceIdentity?
    if !isNullValue(body["identity"]), let value = body["identity"] {
        guard value.isRecord, let displayName = value["displayName"]?.stringValue,
            let email = value["email"]?.stringValue
        else {
            throw CloudClientError.malformed("Connection identity is malformed")
        }
        identity = ServiceIdentity(displayName: displayName, email: email)
    }
    if isNullValue(body["entitlement"]) {
        return ServiceSettingsSnapshot(identity: identity, entitlement: nil)
    }
    guard let entitlementValue = body["entitlement"], entitlementValue.isRecord,
        let limitKey = entitlementValue["limitKey"]?.stringValue, !limitKey.isEmpty,
        let used = entitlementValue["used"]?.numberValue, used.isFinite,
        used >= 0,
        (entitlementValue["limit"]?.isNull ?? true) || entitlementValue["limit"]?.numberValue != nil
    else {
        throw CloudClientError.malformed("Usage allowance response is malformed")
    }
    let limit = entitlementValue["limit"]?.numberValue
    if let limit, !limit.isFinite || limit < 0 {
        throw CloudClientError.malformed("Usage allowance response is malformed")
    }
    return ServiceSettingsSnapshot(
        identity: identity,
        entitlement: ServiceEntitlement(limitKey: limitKey, used: used, limit: limit))
}
