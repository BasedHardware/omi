import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum AudioDownloadState { preparing, downloading, processing, success, error }

/// A presented audio-download progress sheet.
///
/// The sheet owns its lifecycle: [close] pops it with the sheet's **own** context and does nothing
/// once it is gone, so a late close can never pop the page underneath. Back, the scrim and the
/// Cancel button all mean cancel: [cancel] runs `onCancel` once and closes the sheet.
class AudioDownloadSheetHandle {
  AudioDownloadSheetHandle._(this._onCancel);

  final VoidCallback? _onCancel;
  final ValueNotifier<AudioDownloadState> state = ValueNotifier(AudioDownloadState.preparing);
  final ValueNotifier<double> progress = ValueNotifier(0);
  BuildContext? _sheetContext;
  bool _open = true;
  bool _cancelled = false;

  /// Whether the sheet is still on screen.
  bool get isOpen => _open;

  /// Whether the reader cancelled.
  bool get cancelled => _cancelled;

  /// Presents the sheet over [context].
  static AudioDownloadSheetHandle show(BuildContext context, {VoidCallback? onCancel}) {
    final handle = AudioDownloadSheetHandle._(onCancel);
    showOmiSheet<void>(
      context: context,
      showCloseButton: false,
      isDismissible: false,
      enableDrag: false,
      builder: (sheetContext) {
        handle._sheetContext = sheetContext;
        return PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) handle.cancel();
          },
          child: AnimatedBuilder(
            animation: Listenable.merge([handle.state, handle.progress]),
            builder: (context, _) => AudioDownloadProgressSheet(
              state: handle.state.value,
              progress: handle.progress.value,
              onCancel: handle.cancel,
            ),
          ),
        );
      },
    ).whenComplete(() {
      handle._open = false;
      handle._sheetContext = null;
    });
    return handle;
  }

  /// Cancels the download (once) and closes the sheet.
  void cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _onCancel?.call();
    close();
  }

  /// Closes the sheet if it is still open. Safe to call any number of times.
  void close() {
    final sheetContext = _sheetContext;
    if (!_open || sheetContext == null || !sheetContext.mounted) return;
    _open = false;
    Navigator.of(sheetContext).pop();
  }
}

/// The content of the audio-download sheet: a progress ring, the stage, and Cancel while work runs.
class AudioDownloadProgressSheet extends StatelessWidget {
  final AudioDownloadState state;
  final double progress;
  final VoidCallback? onCancel;

  const AudioDownloadProgressSheet({super.key, required this.state, this.progress = 0.0, this.onCancel});

  String _title(BuildContext context) {
    return switch (state) {
      AudioDownloadState.preparing => context.l10n.preparingAudio,
      AudioDownloadState.downloading => context.l10n.downloadingAudioProgress,
      AudioDownloadState.processing => context.l10n.processingAudio,
      AudioDownloadState.success => context.l10n.audioReady,
      AudioDownloadState.error => context.l10n.audioShareFailed,
    };
  }

  Widget _buildIndicator() {
    if (state == AudioDownloadState.success) {
      return Container(
        width: 64,
        height: 64,
        decoration: const BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
        child: const Icon(Icons.check, size: 36, color: OmiColors.success),
      );
    }
    if (state == AudioDownloadState.error) {
      return Container(
        width: 64,
        height: 64,
        decoration: const BoxDecoration(color: OmiColors.dangerSurface, shape: BoxShape.circle),
        child: const Icon(Icons.error_outline, size: 36, color: OmiColors.danger),
      );
    }
    final determinate = state == AudioDownloadState.downloading;
    // A determinate ring shows the download's real progress; OmiSpinner is indeterminate only.
    final value = determinate ? progress : null;
    final ring = CircularProgressIndicator(value: value); // omi-ux-allow: raw-spinner -- determinate
    return SizedBox.square(
      dimension: 64,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox.square(dimension: 64, child: ring),
          if (determinate && progress > 0)
            Text('${(progress * 100).toInt()}%', style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final working = state != AudioDownloadState.success && state != AudioDownloadState.error;
    final title = _title(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xs, OmiSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildIndicator(),
          const SizedBox(height: OmiSpacing.xl),
          Semantics(
            liveRegion: true,
            child: Text(title, style: OmiType.headline, textAlign: TextAlign.center),
          ),
          if (working && onCancel != null) ...[
            const SizedBox(height: OmiSpacing.lg),
            OmiButton.secondary(label: context.l10n.cancel, expand: true, onPressed: onCancel),
          ],
        ],
      ),
    );
  }
}
