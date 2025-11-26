import 'dart:io';
import 'package:desktop_updater/widget/update_widget.dart';
import 'package:flutter/material.dart';
import 'package:omi/services/desktop_update_service.dart';
import 'package:omi/utils/logger.dart';

/// Wrapper widget that adds desktop update functionality to the app
/// This widget wraps the main content and displays update UI when available
class DesktopUpdateWrapper extends StatelessWidget {
  final Widget child;

  const DesktopUpdateWrapper({
    super.key,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    // Only show update UI on desktop platforms
    if (!Platform.isMacOS && !Platform.isWindows && !Platform.isLinux) {
      return child;
    }

    final controller = DesktopUpdateService().controller;

    // If controller is not initialized, just show the child
    if (controller == null) {
      Logger.info('Desktop updater controller not available');
      return child;
    }

    // Use DesktopUpdateWidget which wraps the child and shows updates
    return DesktopUpdateWidget(
      controller: controller,
      child: child,
    );
  }
}
