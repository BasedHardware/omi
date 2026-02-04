import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

/// A shimmer widget that automatically falls back to a static skeleton after a timeout.
///
/// This prevents battery drain from continuous shimmer animations when loading takes
/// longer than expected or fails silently.
///
/// Usage:
/// ```dart
/// ShimmerWithTimeout(
///   timeoutSeconds: 5,
///   baseColor: Colors.grey.shade800,
///   highlightColor: Colors.grey.shade700,
///   child: Container(...),
/// )
/// ```
class ShimmerWithTimeout extends StatefulWidget {
  /// The child widget to apply the shimmer effect to.
  final Widget child;

  /// How long to show the shimmer animation before falling back to static.
  /// Defaults to 5 seconds.
  final int timeoutSeconds;

  /// The base color of the shimmer gradient.
  final Color baseColor;

  /// The highlight color of the shimmer gradient.
  final Color highlightColor;

  /// Optional direction of the shimmer animation.
  final ShimmerDirection direction;

  const ShimmerWithTimeout({
    super.key,
    required this.child,
    this.timeoutSeconds = 5,
    this.baseColor = const Color(0xFF2A2A32),
    this.highlightColor = const Color(0xFF3A3A42),
    this.direction = ShimmerDirection.ltr,
  });

  @override
  State<ShimmerWithTimeout> createState() => _ShimmerWithTimeoutState();
}

class _ShimmerWithTimeoutState extends State<ShimmerWithTimeout> {
  bool _showShimmer = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(Duration(seconds: widget.timeoutSeconds), () {
      if (mounted) {
        setState(() {
          _showShimmer = false;
        });
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_showShimmer) {
      return Shimmer.fromColors(
        baseColor: widget.baseColor,
        highlightColor: widget.highlightColor,
        direction: widget.direction,
        child: widget.child,
      );
    }
    // Static skeleton - same visual but no animation
    return widget.child;
  }
}
