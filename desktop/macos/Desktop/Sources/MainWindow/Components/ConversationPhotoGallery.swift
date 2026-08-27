import AppKit
import OmiTheme
import SwiftUI

enum ConversationPhotoResolver {
  enum ResolutionError: Error, Equatable {
    case invalidInlineImage
    case unavailable
  }

  static func resolve(
    photo: ConversationPhoto,
    conversationID: String,
    remote: @Sendable (String, String) async throws -> Data = { conversationID, photoID in
      try await APIClient.shared.getConversationPhotoImage(
        conversationId: conversationID, photoId: photoID)
    }
  ) async throws -> Data {
    if !photo.base64.isEmpty {
      guard let data = Data(base64Encoded: photo.base64), !data.isEmpty else {
        throw ResolutionError.invalidInlineImage
      }
      return data
    }
    guard !conversationID.isEmpty, photo.storageId?.isEmpty == false else {
      throw ResolutionError.unavailable
    }
    let data = try await remote(conversationID, photo.id)
    guard !data.isEmpty else { throw ResolutionError.unavailable }
    return data
  }
}

private struct ConversationPhotoLoadIdentity: Hashable {
  let conversationID: String
  let photoID: String
  let storageID: String?
  let hasInlineImage: Bool
}

private struct ConversationPhotoImageView: View {
  private enum LoadState {
    case loading
    case loaded(NSImage)
    case failed
  }

  let conversationID: String
  let photo: ConversationPhoto
  @State private var state: LoadState = .loading

  private var identity: ConversationPhotoLoadIdentity {
    ConversationPhotoLoadIdentity(
      conversationID: conversationID,
      photoID: photo.id,
      storageID: photo.storageId,
      hasInlineImage: !photo.base64.isEmpty)
  }

  var body: some View {
    Group {
      switch state {
      case .loading:
        ProgressView()
      case .loaded(let image):
        Image(nsImage: image)
          .resizable()
          .scaledToFill()
      case .failed:
        VStack(spacing: OmiSpacing.xs) {
          Image(systemName: "photo.badge.exclamationmark")
            .scaledFont(size: OmiType.title)
          Text("Photo unavailable")
            .scaledFont(size: OmiType.caption)
        }
        .foregroundColor(Ink.secondary)
      }
    }
    .frame(width: 240, height: 160)
    .background(Ink.rowFillHover)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
    .task(id: identity) {
      state = .loading
      do {
        let data = try await ConversationPhotoResolver.resolve(
          photo: photo, conversationID: conversationID)
        guard let image = NSImage(data: data) else {
          state = .failed
          return
        }
        state = .loaded(image)
      } catch {
        state = .failed
      }
    }
    .accessibilityLabel(photo.description ?? "Conversation photo")
  }
}

struct ConversationPhotoGallery: View {
  let conversationID: String
  let photos: [ConversationPhoto]

  private var visiblePhotos: [ConversationPhoto] {
    photos.filter { !$0.discarded }
  }

  var body: some View {
    if !visiblePhotos.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Photos")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        ScrollView(.horizontal) {
          LazyHStack(spacing: OmiSpacing.md) {
            ForEach(visiblePhotos) { photo in
              ConversationPhotoImageView(conversationID: conversationID, photo: photo)
            }
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
    }
  }
}
