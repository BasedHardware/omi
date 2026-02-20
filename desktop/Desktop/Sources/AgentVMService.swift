import Foundation

/// Manages the cloud agent VM lifecycle: provisioning, status polling, and database upload.
/// All operations are fire-and-forget from the caller's perspective.
actor AgentVMService {
    static let shared = AgentVMService()

    private var isRunning = false

    /// Check backend for existing VM — if none exists, run the full pipeline.
    /// Call this on every app launch for signed-in users.
    func ensureProvisioned() {
        guard !isRunning else {
            log("AgentVMService: Pipeline already running, skipping")
            return
        }
        isRunning = true

        Task {
            defer { isRunning = false }

            // Check backend first
            do {
                let status = try await APIClient.shared.getAgentStatus()
                if let status = status, status.status == "ready", let ip = status.ip {
                    log("AgentVMService: VM already ready — vmName=\(status.vmName) ip=\(ip)")
                    // Only upload if the VM doesn't have a database yet
                    if await checkVMNeedsDatabase(vmIP: ip, authToken: status.authToken) {
                        await uploadDatabase(vmIP: ip, authToken: status.authToken)
                    } else {
                        log("AgentVMService: VM already has database, skipping upload")
                    }
                    await startIncrementalSync(vmIP: ip, authToken: status.authToken)
                    return
                }
                if let status = status,
                   status.status == "provisioning" || status.status == "stopped" {
                    log("AgentVMService: VM is \(status.status), polling until ready...")
                    if let result = await pollUntilReady(maxAttempts: 30, intervalSeconds: 5),
                       let ip = result.ip {
                        log("AgentVMService: VM became ready — ip=\(ip)")
                        if await checkVMNeedsDatabase(vmIP: ip, authToken: result.authToken) {
                            await uploadDatabase(vmIP: ip, authToken: result.authToken)
                        }
                        await startIncrementalSync(vmIP: ip, authToken: result.authToken)
                    }
                    return
                }
                // status is nil or error — fall through to provision
            } catch {
                log("AgentVMService: Status check failed — \(error.localizedDescription), will provision")
            }

            await runPipeline()
        }
    }

    /// Kick off the full VM setup pipeline: provision → poll status → upload DB.
    /// Safe to call multiple times — only one pipeline runs at a time.
    func startPipeline() {
        guard !isRunning else {
            log("AgentVMService: Pipeline already running, skipping")
            return
        }
        isRunning = true

        Task {
            defer { isRunning = false }
            await runPipeline()
        }
    }

    private func runPipeline() async {
        // Step 1: Provision (idempotent — returns existing VM if already provisioned)
        log("AgentVMService: Starting provisioning...")
        let provisionResult: APIClient.AgentProvisionResponse
        do {
            provisionResult = try await APIClient.shared.provisionAgentVM()
            log("AgentVMService: Provision response — vmName=\(provisionResult.vmName) status=\(provisionResult.status) ip=\(provisionResult.ip ?? "none")")
        } catch {
            log("AgentVMService: Provision failed — \(error.localizedDescription)")
            return
        }

        // Step 2: Poll until VM is ready with an IP
        var vmIP = provisionResult.ip
        var authToken = provisionResult.authToken

        if vmIP == nil || provisionResult.agentStatus == "provisioning" {
            log("AgentVMService: Waiting for VM to be ready...")
            let pollResult = await pollUntilReady(maxAttempts: 30, intervalSeconds: 5)
            if let result = pollResult {
                vmIP = result.ip
                authToken = result.authToken
                log("AgentVMService: VM ready — ip=\(vmIP ?? "none")")
            } else {
                log("AgentVMService: VM did not become ready in time")
                return
            }
        }

        guard let ip = vmIP else {
            log("AgentVMService: No IP available after provisioning")
            return
        }

        // Step 3: Check if DB exists and upload it
        await uploadDatabase(vmIP: ip, authToken: authToken)

        // Step 4: Start incremental sync
        await startIncrementalSync(vmIP: ip, authToken: authToken)
    }

    /// Poll GET /v2/agent/status until status is "ready" and IP is available.
    private func pollUntilReady(maxAttempts: Int, intervalSeconds: UInt64) async -> APIClient.AgentStatusResponse? {
        for attempt in 1...maxAttempts {
            do {
                let status: APIClient.AgentStatusResponse? = try await APIClient.shared.getAgentStatus()
                if let status = status, status.status == "ready", status.ip != nil {
                    return status
                }
                if let status = status, status.status == "error" {
                    log("AgentVMService: VM in error state, aborting")
                    return nil
                }
                log("AgentVMService: Poll \(attempt)/\(maxAttempts) — status=\(status?.status ?? "none")")
            } catch {
                log("AgentVMService: Poll error — \(error.localizedDescription)")
            }
            try? await Task.sleep(nanoseconds: intervalSeconds * 1_000_000_000)
        }
        return nil
    }

    /// Check if the VM needs a database upload by hitting its /health endpoint.
    private func checkVMNeedsDatabase(vmIP: String, authToken: String) async -> Bool {
        let healthURL = URL(string: "http://\(vmIP):8080/health")!
        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 10

        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let dbReady = json["databaseReady"] as? Bool {
                return !dbReady
            }
        } catch {
            log("AgentVMService: Health check failed — \(error.localizedDescription)")
        }
        // If we can't reach the health endpoint, assume it needs a DB
        return true
    }

    /// Upload the local omi.db (gzip-compressed) to the VM's /upload endpoint.
    /// Pauses AgentSync during upload to prevent competing for memory and network.
    private func uploadDatabase(vmIP: String, authToken: String) async {
        await AgentSyncService.shared.pause()
        defer { Task { await AgentSyncService.shared.resume() } }
        // Find the local database path
        let dbPath = await MainActor.run {
            let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            let userId = RewindDatabase.currentUserId ?? "anonymous"
            return appSupport
                .appendingPathComponent("Omi", isDirectory: true)
                .appendingPathComponent("users", isDirectory: true)
                .appendingPathComponent(userId, isDirectory: true)
                .appendingPathComponent("omi.db")
        }

        guard FileManager.default.fileExists(atPath: dbPath.path) else {
            log("AgentVMService: Local database not found at \(dbPath.path), skipping upload")
            return
        }

        // Get original file size
        let originalSize: UInt64
        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: dbPath.path)
            originalSize = attrs[.size] as? UInt64 ?? 0
        } catch {
            log("AgentVMService: Failed to get DB size — \(error.localizedDescription)")
            return
        }

        log("AgentVMService: Compressing database (\(originalSize / 1024 / 1024) MB) via streaming gzip...")

        // Stream-compress to a temp file using shell gzip (uses ~0 MB memory vs loading entire DB)
        let tempGzPath = dbPath.appendingPathExtension("upload.gz")
        do {
            // Remove any stale temp file
            try? FileManager.default.removeItem(at: tempGzPath)

            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/gzip")
            process.arguments = ["-c", dbPath.path]

            FileManager.default.createFile(atPath: tempGzPath.path, contents: nil)
            guard let outHandle = FileHandle(forWritingAtPath: tempGzPath.path) else {
                log("AgentVMService: Failed to create temp gzip file")
                return
            }
            process.standardOutput = outHandle
            try process.run()
            process.waitUntilExit()
            try outHandle.close()

            guard process.terminationStatus == 0 else {
                log("AgentVMService: gzip failed with exit code \(process.terminationStatus)")
                try? FileManager.default.removeItem(at: tempGzPath)
                return
            }

            let compressedAttrs = try FileManager.default.attributesOfItem(atPath: tempGzPath.path)
            let compressedSize = compressedAttrs[.size] as? UInt64 ?? 0
            log("AgentVMService: Compressed \(originalSize / 1024 / 1024) MB → \(compressedSize / 1024 / 1024) MB (\(compressedSize * 100 / originalSize)%)")
        } catch {
            log("AgentVMService: Compression failed — \(error.localizedDescription)")
            try? FileManager.default.removeItem(at: tempGzPath)
            return
        }

        log("AgentVMService: Uploading compressed database to \(vmIP)...")

        let uploadURL = URL(string: "http://\(vmIP):8080/upload?token=\(authToken)")!
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue("deflate", forHTTPHeaderField: "Content-Encoding")
        request.timeoutInterval = 600

        do {
            // Upload from file — streams from disk, doesn't load into memory
            let (data, response) = try await URLSession.shared.upload(for: request, fromFile: tempGzPath)
            try? FileManager.default.removeItem(at: tempGzPath)

            guard let httpResponse = response as? HTTPURLResponse else {
                log("AgentVMService: Upload failed — invalid response")
                return
            }

            if httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let bytes = json["bytesReceived"] as? Int {
                    log("AgentVMService: Upload complete — \(bytes / 1024 / 1024) MB received by server")
                } else {
                    log("AgentVMService: Upload complete")
                }
            } else {
                let body = String(data: data, encoding: .utf8) ?? ""
                log("AgentVMService: Upload failed — HTTP \(httpResponse.statusCode): \(body)")
            }
        } catch {
            try? FileManager.default.removeItem(at: tempGzPath)
            log("AgentVMService: Upload failed — \(error.localizedDescription)")
        }
    }

    /// Start incremental sync after VM is confirmed ready.
    private func startIncrementalSync(vmIP: String, authToken: String) async {
        await AgentSyncService.shared.start(vmIP: vmIP, authToken: authToken)
        // Send Firebase token so the VM can call backend tools
        await sendFirebaseToken(vmIP: vmIP, authToken: authToken)
    }

    /// Send the user's Firebase ID token to the VM so it can call Python backend tools.
    private func sendFirebaseToken(vmIP: String, authToken: String) async {
        do {
            let idToken = try await AuthService.shared.getIdToken()
            guard let url = URL(string: "http://\(vmIP):8080/auth?token=\(authToken)") else { return }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 15

            let body: [String: String] = ["firebaseToken": idToken]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return }

            if httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let toolCount = json["toolsRegistered"] as? Int {
                    log("AgentVMService: Firebase token sent to VM (\(toolCount) backend tools registered)")
                } else {
                    log("AgentVMService: Firebase token sent to VM")
                }
            } else {
                let body = String(data: data, encoding: .utf8) ?? ""
                log("AgentVMService: Failed to send Firebase token — HTTP \(httpResponse.statusCode): \(body)")
            }
        } catch {
            log("AgentVMService: Failed to send Firebase token — \(error.localizedDescription)")
        }
    }

}
