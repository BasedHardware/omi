import AppKit
import Combine
import Foundation

final class AppServicesCoordinator {
  var audioCaptureService: AudioCaptureService?
  var transcriptionService: TranscriptionService?
  var systemAudioCaptureService: Any?
  var audioMixer: AudioMixer?
  var meetingDetector: MeetingDetector?
  var vadGateService: VADGateService?
  var localMicService: LocalTranscriptionService?
  var localSystemService: LocalTranscriptionService?

  var maxRecordingTimer: Timer?
  var notificationHealthTimer: Timer?

  var willTerminateObserver: NSObjectProtocol?
  var willSleepObserver: NSObjectProtocol?
  var didWakeObserver: NSObjectProtocol?
  var screenLockedObserver: NSObjectProtocol?
  var screenUnlockedObserver: NSObjectProtocol?
  var screenCapturePermissionLostObserver: NSObjectProtocol?
  var screenCaptureKitBrokenObserver: NSObjectProtocol?
  var systemAudioCaptureModeObserver: NSObjectProtocol?
  var coreAudioCaptureRecoveryObserver: NSObjectProtocol?

  var buttonStreamTask: Task<Void, Never>?
  var bluetoothStateCancellable: AnyCancellable?
  var cancellables = Set<AnyCancellable>()

  deinit {
    maxRecordingTimer?.invalidate()
    notificationHealthTimer?.invalidate()
    buttonStreamTask?.cancel()
    bluetoothStateCancellable?.cancel()
    cancellables.removeAll()
    removeLifecycleObservers()
  }

  func removeLifecycleObservers() {
    if let observer = willTerminateObserver {
      NotificationCenter.default.removeObserver(observer)
      willTerminateObserver = nil
    }
    if let observer = willSleepObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(observer)
      willSleepObserver = nil
    }
    if let observer = didWakeObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(observer)
      didWakeObserver = nil
    }
    if let observer = screenLockedObserver {
      DistributedNotificationCenter.default().removeObserver(observer)
      screenLockedObserver = nil
    }
    if let observer = screenUnlockedObserver {
      DistributedNotificationCenter.default().removeObserver(observer)
      screenUnlockedObserver = nil
    }
    if let observer = screenCapturePermissionLostObserver {
      NotificationCenter.default.removeObserver(observer)
      screenCapturePermissionLostObserver = nil
    }
    if let observer = screenCaptureKitBrokenObserver {
      NotificationCenter.default.removeObserver(observer)
      screenCaptureKitBrokenObserver = nil
    }
    if let observer = systemAudioCaptureModeObserver {
      NotificationCenter.default.removeObserver(observer)
      systemAudioCaptureModeObserver = nil
    }
    if let observer = coreAudioCaptureRecoveryObserver {
      NotificationCenter.default.removeObserver(observer)
      coreAudioCaptureRecoveryObserver = nil
    }
  }
}
