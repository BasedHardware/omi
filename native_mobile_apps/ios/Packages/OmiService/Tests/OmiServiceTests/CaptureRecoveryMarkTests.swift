import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct CaptureRecoveryMarkTests {
    /// Closing the app mid-recording loses phone-mic audio, not an Omi's (it records to its own
    /// storage): only the phone leaves the mark that shows "A recording stopped unexpectedly".
    @Test func onlyPhoneRecordingsMarkAnInterruption() async {
        let phonePrefs = freshPreferences()
        let phone = CaptureStore(
            api: FakeAPIClient(), engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(),
            preferences: phonePrefs, defaultOnDevice: false, userID: { "alice" }
        )
        await phone.startPhone()
        #expect(phonePrefs.string(.captureActiveSince) != nil)

        let omiPrefs = freshPreferences()
        let omi = CaptureStore(
            api: FakeAPIClient(), engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(),
            preferences: omiPrefs, defaultOnDevice: false, userID: { "alice" }
        )
        await omi.startDevice(codec: .opusFS320)
        #expect(omi.isLive)
        #expect(omiPrefs.string(.captureActiveSince) == nil)
    }
}
