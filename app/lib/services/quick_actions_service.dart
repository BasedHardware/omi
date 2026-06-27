import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:quick_actions/quick_actions.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';

const _kAddTask = 'add_task';
const _kAskOmi = 'ask_omi';
const _kVoiceMode = 'voice_mode';
const _kMute = 'mute';
const _kUnmute = 'unmute';
const _kConnectDevice = 'connect_device';
const _kDeviceSettings = 'device_settings';

class QuickActionsService {
  static final QuickActionsService _instance = QuickActionsService._();
  QuickActionsService._();
  static QuickActionsService get instance => _instance;

  final QuickActions _quickActions = const QuickActions();
  bool _initialized = false;

  void initialize(BuildContext context) {
    if (!Platform.isIOS || _initialized) return;
    _initialized = true;

    _quickActions.initialize((shortcutType) {
      _handleShortcut(shortcutType);
    });

    _updateShortcuts(context);
  }

  // Called from HomePage.dispose() so a rebuilt HomePage can re-register the callback.
  void reset() {
    _initialized = false;
  }

  void updateShortcuts(BuildContext context) {
    if (!Platform.isIOS) return;
    _updateShortcuts(context);
  }

  void _updateShortcuts(BuildContext context) {
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);

    final isDeviceConnected = deviceProvider.isConnected;
    final isMuted = captureProvider.recordingState == RecordingState.pause;

    final l10n = context.l10n;

    // iOS displays items in reverse array order (last = top of menu).
    // Desired display (top→bottom): Add Task / Ask Omi Anything / Voice Mode / [Mute|Unmute] / Connect Device|Device Settings
    final items = <ShortcutItem>[
      ShortcutItem(
        type: isDeviceConnected ? _kDeviceSettings : _kConnectDevice,
        localizedTitle: isDeviceConnected ? l10n.deviceSettings : l10n.connectDevice,
      ),
      if (isDeviceConnected)
        ShortcutItem(
          type: isMuted ? _kUnmute : _kMute,
          localizedTitle: isMuted ? l10n.phoneUnmute : l10n.mute,
        ),
      ShortcutItem(type: _kVoiceMode, localizedTitle: l10n.voiceMode),
      ShortcutItem(type: _kAskOmi, localizedTitle: l10n.quickActionAskOmi),
      ShortcutItem(type: _kAddTask, localizedTitle: l10n.addTask),
    ];

    _quickActions.setShortcutItems(items);
  }

  void _handleShortcut(String shortcutType) {
    final navigator = globalNavigatorKey.currentState;
    final context = globalNavigatorKey.currentContext;
    if (navigator == null || context == null) return;

    switch (shortcutType) {
      case _kAddTask:
        _navigateToTasksAndOpenSheet(navigator, context);
        break;
      case _kAskOmi:
        navigator.push(MaterialPageRoute(builder: (_) => const ChatPage(isPivotBottom: false)));
        break;
      case _kVoiceMode:
        navigator.push(MaterialPageRoute(builder: (_) => const ChatPage(isPivotBottom: false, autoStartVoice: true)));
        break;
      case _kMute:
        _toggleMute(context, mute: true);
        break;
      case _kUnmute:
        _toggleMute(context, mute: false);
        break;
      case _kConnectDevice:
        Provider.of<DeviceProvider>(context, listen: false).initiateConnection('QuickActions');
        navigator.push(MaterialPageRoute(builder: (_) => const DeviceSettings()));
        break;
      case _kDeviceSettings:
        navigator.push(MaterialPageRoute(builder: (_) => const DeviceSettings()));
        break;
    }
  }

  void _navigateToTasksAndOpenSheet(NavigatorState navigator, BuildContext context) {
    Provider.of<HomeProvider>(context, listen: false).setIndex(2);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = globalNavigatorKey.currentContext;
      if (ctx == null) return;
      showModalBottomSheet(
        context: ctx,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => const ActionItemFormSheet(),
      );
    });
  }

  void _toggleMute(BuildContext context, {required bool mute}) {
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    if (mute) {
      if (captureProvider.havingRecordingDevice) {
        captureProvider.pauseDeviceRecording();
      } else {
        captureProvider.stopStreamRecording();
      }
    } else {
      if (captureProvider.havingRecordingDevice) {
        captureProvider.resumeDeviceRecording();
      } else {
        captureProvider.streamRecording();
      }
    }
  }
}
