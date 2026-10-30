import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct ChatExtrasMapperTests {
    @Test func readsRatingFollowUpChartAndFiles() throws {
        let json = #"{"id":"m2","text":"Here you go.","sender":"ai","created_at":"2026-10-06T10:00:00Z","rating":-1,"#
            + #""content_blocks":[{"type":"followUp","id":"m2:followup","text":"Want Tuesday too?"}],"#
            + ##""chart_data":{"chart_type":"line","title":"Sleep","datasets":[{"label":"Hours","color":"#4CAF50","##
            + #""data_points":[{"label":"Mon","value":7.5},{"label":"Tue","value":6}]}]},"#
            + #""files":[{"id":"f1","name":"a.jpg","mime_type":"image/jpeg","thumbnail":"https://cdn.example/a.jpg"},"#
            + #"{"id":"f2","name":"b.pdf","mime_type":"application/pdf","thumbnail":""}]}"#
        let message = try #require(ChatMessageMapper.message(fromJSON: Data(json.utf8)))
        #expect(message.serverID == "m2")
        #expect(message.rating == -1)
        #expect(message.followUp == "Want Tuesday too?")
        #expect(message.chart?.kind == .line)
        #expect(message.chart?.series.first?.points.map(\.value) == [7.5, 6])
        #expect(message.chart?.series.first?.color == "#4CAF50")
        #expect(message.files.map(\.id) == ["f1", "f2"])
        #expect(message.files.first?.thumbnailURL?.absoluteString == "https://cdn.example/a.jpg")
        #expect(message.files.last?.thumbnailURL == nil)
        #expect(message.files.first?.isImage == true)
    }

    @Test func plainMessagesHaveNoExtras() throws {
        let json = #"{"id":"m3","text":"Hi","sender":"ai","rating":null,"chart_data":null,"content_blocks":[]}"#
        let message = try #require(ChatMessageMapper.message(fromJSON: Data(json.utf8)))
        #expect(message.rating == nil)
        #expect(message.followUp == nil)
        #expect(message.chart == nil)
        #expect(message.files.isEmpty)
    }

    @Test func typedErrorFramesKeepTheirCode() {
        #expect(ChatStreamEvent.errorCode(#"error: {"error":"quota_exceeded","message":"quota_exceeded"}"#) == "quota_exceeded")
        #expect(ChatStreamEvent.errorCode("error: The response took too long.") == nil)
        #expect(ChatStreamEvent.errorCode("data: hi") == nil)
    }
}
