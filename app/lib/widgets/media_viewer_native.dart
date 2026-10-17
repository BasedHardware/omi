part of 'media_viewer_page.dart';

extension _NativeMediaPresentation on _MediaViewerPageState {
  Future<void> _removeNativeFile(File file) async {
    try {
      if (await file.exists()) await file.delete();
    } catch (_) {/* Temporary file already reclaimed. */}
  }

  Future<String?> _nativeUriFor(int index) => _nativeUris.putIfAbsent(index, () async {
        final session = AuthService.instance.captureSessionSnapshot();
        bool current() => mounted && (session == null || AuthService.instance.isSessionSnapshotCurrent(session));
        try {
          final item = widget.items[index];
          final Uint8List? bytes;
          if (item.bytesLoader != null) {
            bytes = await _bytesFor(index);
          } else if (item.base64 != null) {
            bytes = base64Decode(item.base64!);
          } else {
            // Resolve through the existing image/cache owner. Native UI receives only
            // a temporary container file, never an authenticated storage request.
            final stream = _providerFor(index).resolve(ImageConfiguration.empty);
            final ready = Completer<ui.Image>();
            final listener = ImageStreamListener((info, _) {
              if (!ready.isCompleted) ready.complete(info.image.clone());
            }, onError: (Object error, StackTrace? stack) {
              if (!ready.isCompleted) {
                ready.completeError(error, stack);
              }
            });
            stream.addListener(listener);
            ui.Image? image;
            try {
              image = await ready.future.timeout(_MediaViewerPageState._downloadTimeout);
              final data = await image.toByteData(format: ui.ImageByteFormat.png);
              bytes = data?.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
            } finally {
              stream.removeListener(listener);
              image?.dispose();
            }
          }
          if (!current() || bytes == null || bytes.isEmpty || bytes.length > _MediaViewerPageState._maxDownloadBytes) {
            return null;
          }
          final directory = await getTemporaryDirectory();
          if (!current()) return null;
          final file = File('${directory.path}/omi_native_photo_${DateTime.now().microsecondsSinceEpoch}_$index');
          await file.writeAsBytes(bytes, flush: true);
          if (!current()) {
            await _removeNativeFile(file);
            return null;
          }
          _nativeFiles.add(file);
          return Uri.file(file.path).toString();
        } catch (_) {
          return null;
        }
      });

  Widget _nativeMediaSurface(Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    final index = _currentIndex;
    final item = widget.items[index];
    final l10n = context.l10n;
    return FutureBuilder<String?>(
        future: _nativeUriFor(index),
        builder: (context, result) {
          final loaded = result.connectionState == ConnectionState.done;
          return KeyedSubtree(
              key: _nativeShareKey,
              child: Scaffold(
                  body: IosNativeSurface(
                      title: '${l10n.photos} ${index + 1} / ${widget.items.length}',
                      fallback: classic,
                      loading: !loaded,
                      toolbar: [
                        NativeRow('media_close', l10n.close,
                            symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
                        NativeRow('media_share', l10n.share,
                            symbol: 'square.and.arrow.up', enabled: !_isSharing, action: (_) => _share()),
                      ],
                      sections: [
                        NativeSection('media', [
                          if (result.data != null)
                            NativeRow('media_image', l10n.photos,
                                kind: 'image',
                                imageUri: result.data,
                                maximumValue: widget.maxScaleMultiplier.clamp(1, 16).toDouble()),
                          if (loaded && result.data == null) ...[
                            NativeRow('media_load_error', l10n.somethingWentWrong, kind: 'label'),
                            NativeRow('media_retry', l10n.retry, action: (_) {
                              _nativeUris.remove(index);
                              _onPageChanged(index);
                            }),
                          ],
                          if (item.showCaptionStrip)
                            NativeRow('media_caption',
                                item.discarded ? l10n.photoDiscardedMessage : item.caption ?? l10n.analyzing,
                                kind: 'label'),
                        ])
                      ],
                      reader: NativeReader(request: 0, following: false, footer: [
                        NativeRow('media_previous', l10n.previousResult,
                            symbol: 'chevron.left', enabled: index > 0, action: (_) => _onPageChanged(index - 1)),
                        NativeRow('media_next', l10n.nextButton,
                            symbol: 'chevron.right',
                            enabled: index < widget.items.length - 1,
                            action: (_) => _onPageChanged(index + 1)),
                      ]))));
        });
  }
}
