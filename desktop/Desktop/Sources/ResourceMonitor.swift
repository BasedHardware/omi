import Foundation
import Sentry

/// Monitors system resources (memory, CPU, disk) and reports to Sentry
@MainActor
class ResourceMonitor {
    static let shared = ResourceMonitor()

    /// Check if this is a development build (avoids Sentry calls in dev)
    private let isDevBuild: Bool = Bundle.main.bundleIdentifier?.hasSuffix("-dev") == true

    // MARK: - Configuration

    /// How often to sample resources (seconds)
    private let sampleInterval: TimeInterval = 30

    /// Memory threshold (MB) - warn when exceeded
    private let memoryWarningThreshold: UInt64 = 500

    /// Memory threshold (MB) - critical alert
    private let memoryCriticalThreshold: UInt64 = 800

    /// Memory growth rate threshold (MB/min) - detect leaks
    private let memoryGrowthRateThreshold: Double = 50

    // MARK: - State

    private var monitorTimer: Timer?
    private var isMonitoring = false
    private var memorySamples: [(timestamp: Date, memoryMB: UInt64)] = []
    private let maxSamples = 20 // Keep last 20 samples for trend analysis
    private var lastWarningTime: Date?
    private var lastCriticalTime: Date?
    private var peakMemoryObserved: UInt64 = 0 // Track peak memory manually

    // Minimum time between warnings (prevent spam)
    private let warningCooldown: TimeInterval = 300 // 5 minutes

    private init() {}

    // MARK: - Public API

    /// Start monitoring resources
    func start() {
        guard !isMonitoring else { return }
        isMonitoring = true

        log("ResourceMonitor: Starting resource monitoring (interval: \(Int(sampleInterval))s)")

        // Take initial sample
        Task {
            await sampleResources()
        }

        // Start periodic sampling
        monitorTimer = Timer.scheduledTimer(withTimeInterval: sampleInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.sampleResources()
            }
        }
    }

    /// Stop monitoring resources
    func stop() {
        guard isMonitoring else { return }
        isMonitoring = false
        monitorTimer?.invalidate()
        monitorTimer = nil
        memorySamples.removeAll()
        log("ResourceMonitor: Stopped resource monitoring")
    }

    /// Get current resource snapshot
    func getCurrentResources() -> ResourceSnapshot {
        return ResourceSnapshot(
            memoryUsageMB: getMemoryUsageMB(),
            memoryFootprintMB: getMemoryFootprintMB(),
            peakMemoryMB: getPeakMemoryMB(),
            memoryPercent: getMemoryPercentage(),
            totalSystemRAM_MB: getTotalSystemRAM(),
            systemMemoryPressure: getSystemMemoryPressure(),
            cpuUsage: getCPUUsage(),
            diskUsedGB: getDiskUsedGB(),
            diskFreeGB: getDiskFreeGB(),
            threadCount: getThreadCount(),
            timestamp: Date()
        )
    }

    /// Manually report current resources to Sentry (call before known heavy operations)
    func reportResourcesNow(context: String) {
        let snapshot = getCurrentResources()

        // Add as breadcrumb (skip in dev builds)
        if !isDevBuild {
            let breadcrumb = Breadcrumb(level: .info, category: "resources")
            breadcrumb.message = "[\(context)] Memory: \(snapshot.memoryUsageMB)MB, Footprint: \(snapshot.memoryFootprintMB)MB, CPU: \(String(format: "%.1f", snapshot.cpuUsage))%"
            breadcrumb.data = snapshot.asDictionary()
            SentrySDK.addBreadcrumb(breadcrumb)
        }

        log("ResourceMonitor: [\(context)] \(snapshot.summary)")
    }

    // MARK: - Private Methods

    private func sampleResources() async {
        let snapshot = getCurrentResources()

        // Store memory sample for trend analysis
        memorySamples.append((timestamp: snapshot.timestamp, memoryMB: snapshot.memoryFootprintMB))
        if memorySamples.count > maxSamples {
            memorySamples.removeFirst()
        }

        // Update Sentry context with current resources
        updateSentryContext(snapshot)

        // Check for issues
        checkMemoryThresholds(snapshot)
        checkMemoryGrowthRate()

        // Log periodically (every 5th sample = ~2.5 min)
        if memorySamples.count % 5 == 0 {
            log("ResourceMonitor: \(snapshot.summary)")
        }

        // Log per-component memory diagnostics every 10th sample (~5 min)
        if memorySamples.count % 10 == 0 {
            await logComponentDiagnostics(snapshot: snapshot)
        }
    }

    /// Collect and log per-component memory diagnostics to help identify leak sources
    private func logComponentDiagnostics(snapshot: ResourceSnapshot) async {
        var components: [String: Any] = [:]

        // LiveNotesMonitor buffers (MainActor — direct access)
        let liveNotes = LiveNotesMonitor.shared
        components["liveNotes_wordBuffer"] = liveNotes.wordBufferCount
        components["liveNotes_notesContext"] = liveNotes.existingNotesContextCount
        components["liveNotes_notesCount"] = liveNotes.notes.count

        // VideoChunkEncoder buffer (actor — await)
        let bufferStatus = await VideoChunkEncoder.shared.getBufferStatus()
        components["videoEncoder_frameCount"] = bufferStatus.frameCount
        if let age = bufferStatus.oldestFrameAge {
            components["videoEncoder_oldestFrameAgeSec"] = Int(age)
        }

        // FocusAssistant pending tasks (actor — await, optional since it may not be initialized)
        if let focusAssistant = ProactiveAssistantsPlugin.shared.currentFocusAssistant {
            components["focus_pendingTasks"] = await focusAssistant.pendingTasksCount
            components["focus_historyCount"] = await focusAssistant.analysisHistoryCount
        }

        // Rewind backpressure stats (MainActor — direct access)
        let plugin = ProactiveAssistantsPlugin.shared
        components["rewind_droppedFrames"] = plugin.droppedFrameCount
        components["rewind_isProcessing"] = plugin.isProcessingRewindFrame

        // Thread count is already in snapshot
        components["threadCount"] = snapshot.threadCount

        let componentSummary = components.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ", ")
        log("ResourceMonitor: COMPONENTS: \(componentSummary)")

        // Add to Sentry context for crash diagnostics
        if !isDevBuild {
            SentrySDK.configureScope { scope in
                scope.setContext(value: components, key: "memory_components")
            }

            // Add breadcrumb when memory is elevated
            if snapshot.memoryFootprintMB >= memoryWarningThreshold {
                let breadcrumb = Breadcrumb(level: .warning, category: "memory_diagnostics")
                breadcrumb.message = "Component diagnostics at \(snapshot.memoryFootprintMB)MB"
                breadcrumb.data = components
                SentrySDK.addBreadcrumb(breadcrumb)
            }
        }
    }

    private func updateSentryContext(_ snapshot: ResourceSnapshot) {
        // Set resource context that will be attached to all future events (skip in dev builds)
        guard !isDevBuild else { return }
        SentrySDK.configureScope { scope in
            scope.setContext(value: snapshot.asDictionary(), key: "resources")
        }
    }

    private func checkMemoryThresholds(_ snapshot: ResourceSnapshot) {
        let now = Date()

        // Critical threshold
        if snapshot.memoryFootprintMB >= memoryCriticalThreshold {
            if lastCriticalTime == nil || now.timeIntervalSince(lastCriticalTime!) > warningCooldown {
                lastCriticalTime = now

                logError("ResourceMonitor: CRITICAL - Memory usage \(snapshot.memoryFootprintMB)MB exceeds \(memoryCriticalThreshold)MB threshold")

                // Collect component diagnostics immediately at critical threshold
                Task {
                    await logComponentDiagnostics(snapshot: snapshot)
                }

                // Attempt to free memory by flushing heavy components
                triggerMemoryRemediation()

                // Send Sentry event (skip in dev builds)
                if !isDevBuild {
                    let threshold = self.memoryCriticalThreshold
                    SentrySDK.capture(message: "Critical Memory Usage") { scope in
                        scope.setLevel(.error)
                        scope.setTag(value: "memory_critical", key: "resource_alert")
                        scope.setContext(value: snapshot.asDictionary(), key: "resources")
                        scope.setContext(value: [
                            "threshold_mb": threshold,
                            "current_mb": snapshot.memoryFootprintMB,
                            "peak_mb": snapshot.peakMemoryMB
                        ], key: "memory_details")
                    }
                }
            }
        }
        // Warning threshold
        else if snapshot.memoryFootprintMB >= memoryWarningThreshold {
            if lastWarningTime == nil || now.timeIntervalSince(lastWarningTime!) > warningCooldown {
                lastWarningTime = now

                log("ResourceMonitor: WARNING - Memory usage \(snapshot.memoryFootprintMB)MB exceeds \(memoryWarningThreshold)MB threshold")

                // Add warning breadcrumb (skip in dev builds)
                if !isDevBuild {
                    let breadcrumb = Breadcrumb(level: .warning, category: "resources")
                    breadcrumb.message = "High memory usage: \(snapshot.memoryFootprintMB)MB"
                    breadcrumb.data = snapshot.asDictionary()
                    SentrySDK.addBreadcrumb(breadcrumb)
                }
            }
        }
    }

    private func checkMemoryGrowthRate() {
        guard memorySamples.count >= 5 else { return }

        // Calculate growth rate over last 5 samples
        let recentSamples = Array(memorySamples.suffix(5))
        guard let first = recentSamples.first, let last = recentSamples.last else { return }

        let timeDiffMinutes = last.timestamp.timeIntervalSince(first.timestamp) / 60.0
        guard timeDiffMinutes > 0 else { return }

        let memoryGrowthMB = Double(Int64(last.memoryMB) - Int64(first.memoryMB))
        let growthRateMBPerMin = memoryGrowthMB / timeDiffMinutes

        // Detect potential memory leak
        if growthRateMBPerMin > memoryGrowthRateThreshold {
            log("ResourceMonitor: WARNING - Memory growing at \(String(format: "%.1f", growthRateMBPerMin))MB/min (potential leak)")

            // Add breadcrumb (skip in dev builds)
            if !isDevBuild {
                let breadcrumb = Breadcrumb(level: .warning, category: "resources")
                breadcrumb.message = "Potential memory leak detected: \(String(format: "%.1f", growthRateMBPerMin))MB/min growth rate"
                breadcrumb.data = [
                    "growth_rate_mb_per_min": growthRateMBPerMin,
                    "samples_analyzed": recentSamples.count,
                    "time_span_minutes": timeDiffMinutes,
                    "start_memory_mb": first.memoryMB,
                    "end_memory_mb": last.memoryMB
                ]
                SentrySDK.addBreadcrumb(breadcrumb)
            }
        }
    }

    // MARK: - Memory Remediation

    /// Attempt to free memory by flushing heavy components.
    /// Called at most once per warningCooldown (5 min) when critical threshold is exceeded.
    private func triggerMemoryRemediation() {
        log("ResourceMonitor: Triggering memory remediation — flushing video encoder, clearing assistant pending work, pausing AgentSync")

        let memoryBefore = getMemoryFootprintMB()

        // Clear queued frames in assistant coordinator
        AssistantCoordinator.shared.clearAllPendingWork()

        Task {
            // Flush VideoChunkEncoder and await completion
            _ = try? await VideoChunkEncoder.shared.flushCurrentChunk()

            // Clear focus assistant pending tasks specifically
            if let focusAssistant = ProactiveAssistantsPlugin.shared.currentFocusAssistant {
                await focusAssistant.clearPendingWork()
            }

            // Pause AgentSync to reduce memory pressure and resume after 60s
            await AgentSyncService.shared.pause()
            Task {
                try? await Task.sleep(nanoseconds: 60_000_000_000) // 60s
                await AgentSyncService.shared.resume()
                log("ResourceMonitor: AgentSync resumed after 60s cooldown")
            }

            let memoryAfter = await MainActor.run { self.getMemoryFootprintMB() }
            log("ResourceMonitor: Memory remediation completed — \(memoryBefore)MB -> \(memoryAfter)MB")
        }

        if !isDevBuild {
            let breadcrumb = Breadcrumb(level: .warning, category: "memory_remediation")
            breadcrumb.message = "Memory remediation triggered at critical threshold"
            breadcrumb.data = [
                "memory_footprint_mb": memoryBefore,
                "threshold_mb": memoryCriticalThreshold
            ]
            SentrySDK.addBreadcrumb(breadcrumb)
        }
    }

    // MARK: - Resource Getters (macOS specific)

    /// Get current memory usage in MB (resident set size)
    private func getMemoryUsageMB() -> UInt64 {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size) / 4

        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }

        if result == KERN_SUCCESS {
            return info.resident_size / (1024 * 1024)
        }
        return 0
    }

    /// Get physical memory footprint in MB (more accurate for macOS)
    private func getMemoryFootprintMB() -> UInt64 {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info>.size) / 4

        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }

        if result == KERN_SUCCESS {
            return UInt64(info.phys_footprint) / (1024 * 1024)
        }
        return getMemoryUsageMB() // Fallback
    }

    /// Get peak memory usage in MB (tracked manually since phys_footprint_peak unavailable)
    private func getPeakMemoryMB() -> UInt64 {
        let current = getMemoryFootprintMB()
        if current > peakMemoryObserved {
            peakMemoryObserved = current
        }
        return peakMemoryObserved
    }

    /// Get CPU usage percentage (0-100+, can exceed 100% on multi-core)
    private func getCPUUsage() -> Double {
        var threadList: thread_act_array_t?
        var threadCount: mach_msg_type_number_t = 0

        guard task_threads(mach_task_self_, &threadList, &threadCount) == KERN_SUCCESS,
              let threads = threadList else {
            return 0
        }

        defer {
            vm_deallocate(mach_task_self_, vm_address_t(bitPattern: threads), vm_size_t(threadCount) * vm_size_t(MemoryLayout<thread_t>.size))
        }

        var totalCPU: Double = 0

        for i in 0..<Int(threadCount) {
            var info = thread_basic_info()
            var count = mach_msg_type_number_t(MemoryLayout<thread_basic_info>.size / MemoryLayout<natural_t>.size)

            let result = withUnsafeMutablePointer(to: &info) {
                $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                    thread_info(threads[i], thread_flavor_t(THREAD_BASIC_INFO), $0, &count)
                }
            }

            if result == KERN_SUCCESS && (info.flags & TH_FLAGS_IDLE) == 0 {
                totalCPU += Double(info.cpu_usage) / Double(TH_USAGE_SCALE) * 100.0
            }
        }

        return totalCPU
    }

    /// Get disk space used in GB
    private func getDiskUsedGB() -> Double {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        do {
            let values = try homeDir.resourceValues(forKeys: [.volumeTotalCapacityKey, .volumeAvailableCapacityKey])
            let total = values.volumeTotalCapacity ?? 0
            let available = values.volumeAvailableCapacity ?? 0
            return Double(total - available) / (1024 * 1024 * 1024)
        } catch {
            return 0
        }
    }

    /// Get disk space free in GB
    private func getDiskFreeGB() -> Double {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        do {
            let values = try homeDir.resourceValues(forKeys: [.volumeAvailableCapacityKey])
            return Double(values.volumeAvailableCapacity ?? 0) / (1024 * 1024 * 1024)
        } catch {
            return 0
        }
    }

    /// Get current thread count
    private func getThreadCount() -> Int {
        var threadList: thread_act_array_t?
        var threadCount: mach_msg_type_number_t = 0

        guard task_threads(mach_task_self_, &threadList, &threadCount) == KERN_SUCCESS,
              let threads = threadList else {
            return 0
        }

        vm_deallocate(mach_task_self_, vm_address_t(bitPattern: threads), vm_size_t(threadCount) * vm_size_t(MemoryLayout<thread_t>.size))

        return Int(threadCount)
    }

    /// Get total system RAM in MB
    private func getTotalSystemRAM() -> UInt64 {
        return UInt64(ProcessInfo.processInfo.physicalMemory) / (1024 * 1024)
    }

    /// Get app's memory usage as percentage of total system RAM
    private func getMemoryPercentage() -> Double {
        let totalRAM = getTotalSystemRAM()
        guard totalRAM > 0 else { return 0 }
        let footprint = getMemoryFootprintMB()
        return (Double(footprint) / Double(totalRAM)) * 100.0
    }

    /// Get system-wide memory pressure (percentage of total RAM in use by all apps)
    private func getSystemMemoryPressure() -> Double {
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)

        let result = withUnsafeMutablePointer(to: &stats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count)
            }
        }

        guard result == KERN_SUCCESS else { return 0 }

        let pageSize = UInt64(vm_kernel_page_size)
        let totalRAM = ProcessInfo.processInfo.physicalMemory

        // Active + Wired + Compressed = memory in use
        let activeBytes = UInt64(stats.active_count) * pageSize
        let wiredBytes = UInt64(stats.wire_count) * pageSize
        let compressedBytes = UInt64(stats.compressor_page_count) * pageSize
        let usedBytes = activeBytes + wiredBytes + compressedBytes

        return (Double(usedBytes) / Double(totalRAM)) * 100.0
    }
}

// MARK: - Resource Snapshot

struct ResourceSnapshot {
    let memoryUsageMB: UInt64      // Resident set size
    let memoryFootprintMB: UInt64  // Physical footprint (more accurate)
    let peakMemoryMB: UInt64       // Peak memory since launch
    let memoryPercent: Double      // App memory as % of total RAM
    let totalSystemRAM_MB: UInt64  // Total system RAM
    let systemMemoryPressure: Double // System-wide RAM usage %
    let cpuUsage: Double           // CPU percentage
    let diskUsedGB: Double         // Disk used
    let diskFreeGB: Double         // Disk free
    let threadCount: Int           // Number of threads
    let timestamp: Date

    var summary: String {
        "Memory: \(memoryFootprintMB)MB/\(totalSystemRAM_MB / 1024)GB (\(String(format: "%.2f", memoryPercent))%), System RAM: \(String(format: "%.1f", systemMemoryPressure))% used, CPU: \(String(format: "%.1f", cpuUsage))%, Threads: \(threadCount)"
    }

    func asDictionary() -> [String: Any] {
        return [
            "memory_usage_mb": memoryUsageMB,
            "memory_footprint_mb": memoryFootprintMB,
            "peak_memory_mb": peakMemoryMB,
            "memory_percent": memoryPercent,
            "total_system_ram_mb": totalSystemRAM_MB,
            "system_memory_pressure_percent": systemMemoryPressure,
            "cpu_usage_percent": cpuUsage,
            "disk_used_gb": diskUsedGB,
            "disk_free_gb": diskFreeGB,
            "thread_count": threadCount,
            "timestamp": ISO8601DateFormatter().string(from: timestamp)
        ]
    }
}
