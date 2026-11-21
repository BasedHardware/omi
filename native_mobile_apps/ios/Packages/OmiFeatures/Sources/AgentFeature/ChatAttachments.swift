import OmiCore
import OmiDesign
import OmiService
import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// The composer's "+": a photo from the library, a new photo, a file (Flutter `selectImage`,
/// camera, `selectFile`), or a photo or screenshot on the clipboard. Each one uploads as soon as it
/// is picked; photos go up as JPEG (`ChatImageEncoder`: the backend refuses HEIC).
struct AttachmentButton: View {
    @Environment(ChatStore.self) private var chat
    @State private var showsLibrary = false
    @State private var showsCamera = false
    @State private var showsFiles = false
    @State private var photos: [PhotosPickerItem] = []

    /// The document types Flutter offers, plus any image.
    private static let fileTypes: [UTType] = [.image, .pdf, .plainText]
        + ["md", "doc", "docx", "pptx", "xlsx"].compactMap { UTType(filenameExtension: $0) }

    var body: some View {
        Menu {
            Button { showsLibrary = true } label: { Label(L("photoLibrary"), systemImage: "photo.on.rectangle") }
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button { showsCamera = true } label: { Label(L("takePhoto"), systemImage: "camera") }
            }
            Button { showsFiles = true } label: { Label(L("chooseFile"), systemImage: "doc") }
            if UIPasteboard.general.hasImages {
                Button(action: pastePhotos) { Label(L("nativeChatPastePhoto"), systemImage: "doc.on.clipboard") }
            }
        } label: {
            // A round chip beside the field, the same size as the mic on the other side.
            Image(systemName: "plus")
                .font(.system(size: 18, weight: .regular))
                .foregroundStyle(chat.canAttach ? DS.Palette.ink : DS.Palette.inkDisabled)
                .frame(width: DS.Size.composer, height: DS.Size.composer)
                .background(DS.Palette.card, in: Circle())
                .overlay { Circle().strokeBorder(DS.Palette.cardStroke, lineWidth: 0.5) }
                .contentShape(Circle())
        }
        .disabled(!chat.canAttach)
        .accessibilityLabel(L("nativeAttach"))
        .accessibilityIdentifier("chat.attach")
        .photosPicker(
            isPresented: $showsLibrary, selection: $photos,
            maxSelectionCount: max(1, ChatStore.maxAttachments - chat.attachments.count), matching: .images
        )
        .onChange(of: photos) { _, items in
            guard !items.isEmpty else { return }
            photos = []
            Task {
                for item in items {
                    // Library photos are often HEIC: converted to JPEG on the way up.
                    if let data = try? await item.loadTransferable(type: Data.self) { chat.attachImage(data: data) }
                }
            }
        }
        .fullScreenCover(isPresented: $showsCamera) {
            CameraPicker { attach($0) }.ignoresSafeArea()
        }
        .fileImporter(isPresented: $showsFiles, allowedContentTypes: Self.fileTypes, allowsMultipleSelection: true) { result in
            guard case let .success(urls) = result else { return }
            for url in urls { attachFile(url) }
        }
    }

    /// Photos travel as JPEG (HEIC is not accepted), at most 2048 px on the long side.
    private func attach(_ image: UIImage) {
        guard let data = image.scaled(toFit: CGFloat(ChatImageEncoder.maxSide)).jpegData(compressionQuality: 0.9) else { return }
        chat.attachImage(data: data)
    }

    /// Photos or screenshots copied elsewhere, as they are on the clipboard (HEIC, PNG …).
    private func pastePhotos() {
        let board = UIPasteboard.general
        let types = [UTType.heic, .heif, .png, .jpeg, .tiff, .image].map(\.identifier)
        var raw: [Data] = []
        for index in 0 ..< board.numberOfItems where raw.count < ChatStore.maxAttachments {
            let item = IndexSet(integer: index)
            if let data = types.lazy.compactMap({ board.data(forPasteboardType: $0, inItemSet: item)?.first }).first {
                raw.append(data)
            }
        }
        if raw.isEmpty { raw = (board.images ?? []).compactMap { $0.jpegData(compressionQuality: 0.95) } }
        for data in raw.prefix(ChatStore.maxAttachments - chat.attachments.count) {
            chat.attachImage(data: data)
        }
    }

    private func attachFile(_ url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else { return }
        let type = UTType(filenameExtension: url.pathExtension)
        if type?.conforms(to: .image) == true, chat.attachImage(data: data, filename: url.lastPathComponent) { return }
        let mimeType = type?.preferredMIMEType ?? "application/octet-stream"
        chat.attach(data: data, filename: url.lastPathComponent, mimeType: mimeType, preview: nil)
    }
}

/// What is attached to the next message: thumbnails with a spinner while uploading, a warning when
/// the upload failed, and a remove button.
struct AttachmentStrip: View {
    @Environment(ChatStore.self) private var chat

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: DS.Spacing.sm) {
                ForEach(chat.attachments) { attachment in
                    Group {
                        if attachment.preview != nil {
                            AttachmentThumbnail(preview: attachment.preview).frame(width: 56, height: 56)
                        } else {
                            DocumentChip(name: attachment.filename).frame(height: 56)
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                    .overlay {
                        switch attachment.state {
                        case .uploading: ProgressView().controlSize(.small)
                        case .failed:
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(DS.Palette.live)
                                .accessibilityLabel(L("nativeAttachmentFailed"))
                        case .uploaded: EmptyView()
                        }
                    }
                    .overlay(alignment: .topTrailing) {
                        Button { chat.removeAttachment(attachment.id) } label: {
                            Image(systemName: "xmark.circle.fill")
                                .symbolRenderingMode(.palette)
                                .foregroundStyle(.white, .black.opacity(0.6))
                        }
                        .buttonStyle(.plain)
                        .offset(x: 6, y: -6)
                        .accessibilityLabel(L("nativeRemoveAttachment"))
                    }
                }
            }
            .padding(.top, DS.Spacing.sm)
            .padding(.trailing, DS.Spacing.sm)
        }
    }
}

/// The camera, for "Take photo".
private struct CameraPicker: UIViewControllerRepresentable {
    let onPhoto: (UIImage) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_: UIImagePickerController, context _: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker

        init(_ parent: CameraPicker) {
            self.parent = parent
        }

        func imagePickerController(_: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage { parent.onPhoto(image) }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

private extension UIImage {
    func scaled(toFit side: CGFloat) -> UIImage {
        let longest = max(size.width, size.height)
        guard longest > side else { return self }
        let factor = side / longest
        let target = CGSize(width: size.width * factor, height: size.height * factor)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: target, format: format).image { _ in draw(in: CGRect(origin: .zero, size: target)) }
    }
}
