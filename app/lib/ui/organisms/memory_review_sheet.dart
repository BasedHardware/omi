library memory_review_sheet_organism;

import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'desktop/memory_review_sheet_desktop.dart' as desktop;
import 'mobile/memory_review_sheet_mobile.dart' as mobile;

/// Runtime wrapper: picks the right implementation for the current platform.
class MemoryReviewSheet extends StatelessWidget {
  final List<Memory> memories;
  final MemoriesProvider provider;
  final VoidCallback onClose;

  const MemoryReviewSheet({
    super.key,
    required this.memories,
    required this.provider,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final isMobile = defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;
    if (isMobile) {
      return mobile.MobileMemoryReviewSheet(
        memories: memories,
        provider: provider,
        onClose: onClose,
      );
    }
    return desktop.DesktopMemoryReviewSheet(
      memories: memories,
      provider: provider,
      onClose: onClose,
    );
  }
}
