import Foundation
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct PhoneVerificationTests {
    let api = FakeAPIClient()
    let engine = FakeCallEngine()

    @Test func verifyingShowsTheCodeThenStoresTheNumber() async {
        let store = await phoneStore(api: api, engine: engine, verified: false)
        #expect(store.numbers.isEmpty && store.numbersLoaded)
        #expect(await store.startVerification("+4915112345678"))
        #expect(store.verification?.code == "123456")
        #expect(store.verification?.status == .calling)
        #expect(api.phoneCalls.verifyRequests == ["+4915112345678"])

        api.phoneCalls.checkAnswers = [false, false, true]
        await store.pollVerification()
        #expect(store.verification?.status == .verified)
        #expect(api.phoneCalls.checkRequests.count == 3)
        #expect(store.numbers.map(\.phoneNumber) == ["+4915112345678"])
    }

    @Test func anUnansweredCallIsMissedThenTimesOut() async {
        let store = await phoneStore(api: api, engine: engine, verified: false)
        await store.startVerification("+4915112345678")
        await store.pollVerification()
        #expect(store.verification?.status == .timedOut)
        #expect(api.phoneCalls.checkRequests.count == 30)
    }

    @Test func statusMovesFromCallingToInProgressToMissed() async throws {
        var timing = PhoneCallStore.Timing()
        timing.verificationPoll = .milliseconds(10)
        let store = PhoneCallStore(api: api, engine: engine, userID: { "u" }, timing: timing)
        await store.startVerification("+4915112345678")
        let poll = Task { await store.pollVerification() }
        try await waitUntil { store.verification?.status == .inProgress }
        #expect(store.verification?.status == .inProgress)
        try await waitUntil { store.verification?.status == .missed }
        #expect(store.verification?.status == .missed)
        poll.cancel()
    }

    @Test func retryingCallsAgainAndPolls() async {
        let store = await phoneStore(api: api, engine: engine, verified: false)
        await store.startVerification("+4915112345678")
        await store.pollVerification()
        api.phoneCalls.checkAnswers = [true]
        await store.retryVerification()
        #expect(api.phoneCalls.verifyRequests.count == 2)
        #expect(store.verification?.status == .verified)
    }

    @Test func theBackendsRefusalIsShown() async {
        api.phoneCalls.verifyError = .http(status: 409, body: #"{"detail":"Phone number already verified"}"#)
        let store = await phoneStore(api: api, engine: engine, verified: false)
        #expect(await store.startVerification("+4915112345678") == false)
        #expect(store.verificationFailure == .server(.message("Phone number already verified")))
        #expect(store.verification == nil)
    }

    @Test func anAlreadyVerifiedNumberNeedsNoCall() async {
        api.phoneCalls.verification = PhoneVerification(phoneNumber: "", validationCode: nil, status: "verified")
        let store = await phoneStore(api: api, engine: engine, verified: false)
        await store.startVerification("+4915112345678")
        #expect(store.verification?.status == .verified)
        await store.pollVerification()
        #expect(api.phoneCalls.checkRequests.isEmpty)
    }

    @Test func deletingRemovesTheNumberOnlyWhenTheBackendDid() async {
        let store = await phoneStore(api: api, engine: engine)
        api.phoneCalls.deleteError = .http(status: 503, body: #"{"detail":"Could not remove the phone number."}"#)
        #expect(await store.deleteNumber("n1") == false)
        #expect(store.numbers.count == 1)
        api.phoneCalls.deleteError = nil
        #expect(await store.deleteNumber("n1"))
        #expect(store.numbers.isEmpty)
        #expect(api.phoneCalls.deleted == ["n1"])
    }

    @Test func aPlanWithoutCallsIsUnavailable() async {
        api.fail(with: .http(status: 403, body: #"{"detail":"Phone calls require a paid subscription"}"#))
        let store = await phoneStore(api: api, engine: engine)
        #expect(store.unavailable == .message("Phone calls require a paid subscription"))
        #expect(store.numbers.isEmpty)
    }

    @Test func signingOutEndsTheCallAndForgetsTheNumbers() async {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        store.clearUserData()
        #expect(engine.ended == 1)
        #expect(store.phase == .idle && store.numbers.isEmpty && !store.numbersLoaded)
    }
}

struct PhoneNumberFormatTests {
    @Test func theKeypadAddsTheCallersCountryCode() {
        #expect(PhoneNumberFormat.dialable("(555) 123-4567", callerNumber: "+15551112222") == "+15551234567")
        #expect(PhoneNumberFormat.dialable("030 1234.567", callerNumber: "+4915112345678") == "+49301234567")
        #expect(PhoneNumberFormat.dialable("0044 20 7946 0958", callerNumber: "+4915112345678") == "+442079460958")
        #expect(PhoneNumberFormat.dialable("+44 20 7946 0958", callerNumber: "+15551112222") == "+442079460958")
        #expect(PhoneNumberFormat.dialable("5551234", callerNumber: nil) == "5551234")
    }

    @Test func callingCodesMatchLongestFirst() {
        #expect(PhoneNumberFormat.callingCode(ofE164: "+15551112222") == "1")
        #expect(PhoneNumberFormat.callingCode(ofE164: "+4915112345678") == "49")
        #expect(PhoneNumberFormat.callingCode(ofE164: "+971501234567") == "971")
        #expect(PhoneNumberFormat.callingCode(ofE164: "+353861234567") == "353")
        #expect(PhoneNumberFormat.callingCode(ofE164: "4915112345678") == nil)
    }

    @Test func setupTurnsANationalNumberIntoE164() {
        #expect(PhoneNumberFormat.e164(national: "0151 1234 5678", region: "DE") == "+4915112345678")
        #expect(PhoneNumberFormat.e164(national: "(555) 123-4567", region: "US") == "+15551234567")
        #expect(PhoneNumberFormat.e164(national: "1 555 123 4567", region: "US") == "+15551234567")
        #expect(PhoneNumberFormat.e164(national: "06 1234 5678", region: "IT") == "+390612345678")
        #expect(PhoneNumberFormat.e164(national: "+44 20 7946 0958", region: "DE") == "+442079460958")
        #expect(PhoneNumberFormat.e164(national: "0044 20 7946 0958", region: "DE") == "+442079460958")
        #expect(PhoneNumberFormat.e164(national: "123", region: "DE") == nil)
        #expect(PhoneNumberFormat.e164(national: "12ab45678", region: "DE") == nil)
    }

    @Test func numbersReadInGroups() {
        #expect(PhoneNumberFormat.display("+15551234567") == "+1 555 123 4567")
        #expect(PhoneNumberFormat.display("+4915112345678") == "+49 151 123 456 78")
        #expect(PhoneNumberFormat.display("5551234") == "5551234")
    }
}
