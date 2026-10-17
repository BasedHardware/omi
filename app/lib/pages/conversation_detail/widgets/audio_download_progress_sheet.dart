import 'package:flutter/material.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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

  /// [close] arrived before the sheet first built; it closes as soon as it has a context.
  bool _closeRequested = false;

  /// Whether the sheet is still on screen.
  bool get isOpen => _open;

  /// Whether the reader cancelled.
  bool get cancelled => _cancelled;

  /// Presents the sheet over [context].
  ///
  /// [nativeContentForTest] builds the native content inside the Flutter sheet, so a hermetic test
  /// reaches the native wiring that only an iOS host with the flag would otherwise present.
  static AudioDownloadSheetHandle show(BuildContext context,
      {VoidCallback? onCancel, @visibleForTesting bool nativeContentForTest = false}) {
    final handle = AudioDownloadSheetHandle._(onCancel);
    showOmiSheet<void>(
      context: context,
      showCloseButton: false,
      isDismissible: false,
      enableDrag: false,
      builder: (sheetContext) => handle._present(sheetContext, native: nativeContentForTest),
      nativeBuilder: (sheetContext) => handle._present(sheetContext, native: true),
    ).whenComplete(() {
      handle._open = false;
      handle._sheetContext = null;
    });
    return handle;
  }

  /// Back means cancel in both presentations; the native one keeps the Flutter content as its
  /// fallback inside the usual sheet shell.
  Widget _present(BuildContext sheetContext, {required bool native}) {
    _sheetContext = sheetContext;
    if (_closeRequested) {
      _closeRequested = false;
      WidgetsBinding.instance.addPostFrameCallback((_) => close());
    }
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) cancel();
      },
      child: AnimatedBuilder(
        animation: Listenable.merge([state, progress]),
        builder: (context, _) {
          final content = AudioDownloadProgressSheet(state: state.value, progress: progress.value, onCancel: cancel);
          if (!native) return content;
          return AudioDownloadNativeSheet(
            state: state.value,
            progress: progress.value,
            onCancel: cancel,
            fallback: OmiSheetScaffold(showCloseButton: false, child: content),
          );
        },
      ),
    );
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
    if (!_open) return;
    if (sheetContext == null) {
      // The route is not built yet (the native check is asynchronous): close once it is.
      _closeRequested = true;
      return;
    }
    if (!sheetContext.mounted) return;
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

  /// The stage's copy, shared with the native sheet.
  String title(BuildContext context) {
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
        decoration: BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
        child: Icon(Icons.check, size: 36, color: OmiColors.success),
      );
    }
    if (state == AudioDownloadState.error) {
      return Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(color: OmiColors.dangerSurface, shape: BoxShape.circle),
        child: Icon(Icons.error_outline, size: 36, color: OmiColors.danger),
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
    final title = this.title(context);
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

/// The native audio-download sheet: the stage, the download's progress, the outcome and Cancel
/// while work runs. It cannot be swiped away; Back maps to cancel through the handle's PopScope.
class AudioDownloadNativeSheet extends StatelessWidget {
  const AudioDownloadNativeSheet(
      {super.key, required this.state, required this.progress, required this.fallback, this.onCancel});

  final AudioDownloadState state;
  final double progress;
  final VoidCallback? onCancel;
  final Widget fallback;

  /// The download fraction the progress row may show: finite and within 0...1.
  static double clampedProgress(double value) => value.isFinite ? value.clamp(0.0, 1.0).toDouble() : 0.0;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final title = AudioDownloadProgressSheet(state: state).title(context);
    final working = state != AudioDownloadState.success && state != AudioDownloadState.error;
    final fraction = clampedProgress(progress);
    return IosNativeSurface(
      title: title,
      loading: state == AudioDownloadState.preparing || state == AudioDownloadState.processing,
      loadingLabel: title,
      fallback: fallback,
      sections: [
        NativeSection('audio_download', [
          // Preparing and processing show the surface's activity row; downloading shows its progress.
          if (state == AudioDownloadState.success)
            NativeRow('audio_download_status', title, kind: 'label', symbol: 'checkmark.circle.fill')
          else if (state == AudioDownloadState.error)
            NativeRow('audio_download_status', title,
                kind: 'label', symbol: 'exclamationmark.circle.fill', destructive: true),
          if (state == AudioDownloadState.downloading)
            NativeRow('audio_download_progress', title,
                kind: 'progress',
                value: fraction,
                maximumValue: 1,
                subtitle: fraction > 0 ? '${(fraction * 100).toInt()}%' : ''),
          if (working && onCancel != null)
            NativeRow('audio_download_cancel', l10n.cancel, destructive: true, action: (_) => onCancel!()),
        ]),
      ],
    );
  }
}
