import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/utils/l10n_extensions.dart';

enum AudioDownloadState {
  preparing,
  downloading,
  processing,
  success,
  error,
}

class AudioDownloadProgressSheet extends StatefulWidget {
  final AudioDownloadState state;
  final double progress;
  final String? errorMessage;
  final VoidCallback? onRetry;
  final VoidCallback? onCancel;

  const AudioDownloadProgressSheet({
    super.key,
    required this.state,
    this.progress = 0.0,
    this.errorMessage,
    this.onRetry,
    this.onCancel,
  });

  @override
  State<AudioDownloadProgressSheet> createState() => _AudioDownloadProgressSheetState();

  static Future<void> show({
    required BuildContext context,
    required AudioDownloadState state,
    double progress = 0.0,
    String? errorMessage,
    VoidCallback? onRetry,
    VoidCallback? onCancel,
  }) {
    return showModalBottomSheet(
      context: context,
      isDismissible: state == AudioDownloadState.error,
      enableDrag: state == AudioDownloadState.error,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withOpacity(0.5),
      builder: (ctx) => AudioDownloadProgressSheet(
        state: state,
        progress: progress,
        errorMessage: errorMessage,
        onRetry: onRetry,
        onCancel: onCancel,
      ),
    );
  }
}

class _AudioDownloadProgressSheetState extends State<AudioDownloadProgressSheet> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _scaleAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    );
    _animationController.forward();

    HapticFeedback.lightImpact();
  }

  @override
  void didUpdateWidget(AudioDownloadProgressSheet oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      HapticFeedback.selectionClick();
    }
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scaleAnimation,
      child: Container(
        margin: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.4),
              blurRadius: 30,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildProgressIndicator(),
              const SizedBox(height: 24),
              _buildTitle(),
              if (widget.state == AudioDownloadState.error) _buildErrorActions(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildProgressIndicator() {
    if (widget.state == AudioDownloadState.success) {
      return TweenAnimationBuilder<double>(
        tween: Tween(begin: 0.0, end: 1.0),
        duration: const Duration(milliseconds: 400),
        builder: (context, value, child) {
          return Transform.scale(
            scale: value,
            child: Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.15),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.check,
                size: 36,
                color: Colors.green,
              ),
            ),
          );
        },
      );
    }

    if (widget.state == AudioDownloadState.error) {
      return Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          color: Colors.red.withOpacity(0.15),
          shape: BoxShape.circle,
        ),
        child: const Icon(
          Icons.error_outline,
          size: 36,
          color: Colors.red,
        ),
      );
    }

    return SizedBox(
      width: 64,
      height: 64,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 64,
            height: 64,
            child: CircularProgressIndicator(
              value: widget.state == AudioDownloadState.downloading ? widget.progress : null,
              strokeWidth: 3,
              valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
              backgroundColor: const Color(0xFF3A3A3C),
            ),
          ),
          if (widget.state == AudioDownloadState.downloading && widget.progress > 0)
            Text(
              '${(widget.progress * 100).toInt()}%',
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Colors.white,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildTitle() {
    String title;

    switch (widget.state) {
      case AudioDownloadState.preparing:
        title = context.l10n.preparingAudio;
        break;
      case AudioDownloadState.downloading:
        title = context.l10n.downloadingAudioProgress;
        break;
      case AudioDownloadState.processing:
        title = context.l10n.processingAudio;
        break;
      case AudioDownloadState.success:
        title = context.l10n.audioReady;
        break;
      case AudioDownloadState.error:
        title = context.l10n.audioShareFailed;
        break;
    }

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 250),
      child: Text(
        title,
        key: ValueKey(title),
        style: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: Colors.white,
          letterSpacing: 0.3,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }

  Widget _buildErrorActions() {
    return Column(
      children: [
        const SizedBox(height: 12),
        Text(
          widget.errorMessage ?? context.l10n.audioDownloadFailed,
          style: TextStyle(
            fontSize: 14,
            color: Colors.grey[400],
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () => Navigator.of(context).pop(),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.grey[300],
                  side: const BorderSide(color: Color(0xFF3A3A3C)),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: Text(context.l10n.close),
              ),
            ),
            if (widget.onRetry != null) ...[
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.of(context).pop();
                    widget.onRetry?.call();
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: const Color(0xFF1C1C1E),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    elevation: 0,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: Text(context.l10n.retry),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}
