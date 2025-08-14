import 'package:flutter/material.dart';

/// Enum representing available action item integrations
enum ActionItemIntegration {
  appleReminders('Apple Reminders', 'apple-reminders-logo.png', false, null),
  appleNotes('Apple Notes', 'apple-notes-logo.png', false, null),
  appleCalendar('Apple Calendar', 'apple-calendar-logo.png', false, null);

  final String displayName;
  final String? assetPath;
  final bool isSvg;
  final IconData? icon;

  const ActionItemIntegration(this.displayName, this.assetPath, this.isSvg, this.icon);
  
  String? get fullAssetPath => assetPath != null ? 'assets/images/$assetPath' : null;
  
  bool get hasAsset => assetPath != null;
}