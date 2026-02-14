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
                    await uploadDatabase(vmIP: ip, authToken: status.authToken)
                    return
                }
                if let status = status, status.status == "provisioning" {
                    log("AgentVMService: VM is provisioning, polling...")
                    if let result = await pollUntilReady(maxAttempts: 30, intervalSeconds: 5),
                       let ip = result.ip {
                        log("AgentVMService: VM became ready — ip=\(ip)")
                        await uploadDatabase(vmIP: ip, authToken: result.authToken)
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

    /// Upload the local omi.db (gzip-compressed) to the VM's /upload endpoint.
    private func uploadDatabase(vmIP: String, authToken: String) async {
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

        log("AgentVMService: Compressing database (\(originalSize / 1024 / 1024) MB)...")

        // Gzip compress the database
        let compressedData: Data
        do {
            let rawData = try Data(contentsOf: dbPath)
            compressedData = try gzipCompress(rawData)
            log("AgentVMService: Compressed \(originalSize / 1024 / 1024) MB → \(compressedData.count / 1024 / 1024) MB (\(compressedData.count * 100 / Int(originalSize))%)")
        } catch {
            log("AgentVMService: Compression failed — \(error.localizedDescription)")
            return
        }

        log("AgentVMService: Uploading compressed database (\(compressedData.count / 1024 / 1024) MB) to \(vmIP)...")

        let uploadURL = URL(string: "http://\(vmIP):8080/upload?token=\(authToken)")!
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue("deflate", forHTTPHeaderField: "Content-Encoding")
        request.setValue(String(compressedData.count), forHTTPHeaderField: "Content-Length")
        request.timeoutInterval = 600

        do {
            let (data, response) = try await URLSession.shared.upload(for: request, from: compressedData)
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
            log("AgentVMService: Upload failed — \(error.localizedDescription)")
        }
    }

    /// Gzip compress data using Apple's Compression framework.
    private func gzipCompress(_ data: Data) throws -> Data {
        // Use NSData's built-in compressed method (available macOS 10.15+)
        let nsData = data as NSData
        guard let compressed = try? nsData.compressed(using: .zlib) else {
            throw NSError(domain: "AgentVMService", code: -1, userInfo: [NSLocalizedDescriptionKey: "Compression failed"])
        }
        return compressed as Data
    }
}
