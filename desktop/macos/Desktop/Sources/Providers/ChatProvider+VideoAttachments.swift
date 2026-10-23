import Foundation

/// Chat video attachments: a clip is sampled on device (frames + audio) and uploaded to
/// `/v2/files/video`, so the whole file never leaves the Mac.
extension ChatProvider {
  func uploadVideoAttachment(id: String, url: URL, fileName: String, appId: String?) async {
    do {
      let video = try await ChatVideoSampler.sample(url: url)
      let resp = try await APIClient.shared.uploadChatVideo(video, fileName: fileName, appId: appId)
      guard let server = resp.first else { throw APIError.invalidResponse }
      guard let idx = pendingAttachments.firstIndex(where: { $0.id == id }) else { return }
      pendingAttachments[idx].serverId = server.id
      pendingAttachments[idx].thumbnailURL = server.thumbnail
      if let mime = server.mimeType { pendingAttachments[idx].mimeType = mime }
      if let name = server.name { pendingAttachments[idx].fileName = name }
      pendingAttachments[idx].state = .uploaded
    } catch {
      logError("ChatProvider: video attachment upload failed", error: error)
      if let idx = pendingAttachments.firstIndex(where: { $0.id == id }) {
        pendingAttachments[idx].state = .failed(error.localizedDescription)
      }
    }
  }
}
