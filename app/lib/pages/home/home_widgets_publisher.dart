import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/home_widgets_service.dart';

/// Keeps the iOS Home Screen widgets in step with the app: the wearables (Devices), the next open
/// tasks (Up next) and the latest conversation (Latest). Changes are gathered for a moment
/// and written only when a document changed; leaving the app writes at once.
class HomeWidgetsPublisher with WidgetsBindingObserver {
  HomeWidgetsPublisher({
    required this.devices,
    required this.tasks,
    required this.conversations,
    required this.l10n,
    HomeWidgetsService? service,
    this.delay = const Duration(milliseconds: 800),
  }) : service = service ?? HomeWidgetsService.instance;

  final DeviceProvider devices;
  final ActionItemsProvider tasks;
  final ConversationProvider conversations;
  final AppLocalizations Function() l10n;
  final HomeWidgetsService service;
  final Duration delay;
  Timer? _timer;

  void start() {
    devices.addListener(_schedule);
    tasks.addListener(_schedule);
    conversations.addListener(_schedule);
    WidgetsBinding.instance.addObserver(this);
    _schedule();
  }

  void dispose() {
    _timer?.cancel();
    devices.removeListener(_schedule);
    tasks.removeListener(_schedule);
    conversations.removeListener(_schedule);
    WidgetsBinding.instance.removeObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) publishNow();
  }

  void _schedule() {
    _timer?.cancel();
    _timer = Timer(delay, publishNow);
  }

  /// Writes what the widgets show now. Up next waits for the task list to load (an empty list
  /// before then is not "All caught up"); Latest waits for a conversation to show.
  @visibleForTesting
  void publishNow() {
    _timer?.cancel();
    unawaited(service.publish(
      HomeWidgetsService.devicesKey,
      HomeWidgetsPayload.devices(
        saved: SharedPreferencesUtil().btDevices,
        connected: devices.connectedDevice,
        isConnected: devices.isConnected,
        battery: devices.batteryLevel,
        charging: devices.isCharging,
      ),
    ));
    if (tasks.hasLoaded) {
      final open = tasks.incompleteItems;
      unawaited(service.publish(
        HomeWidgetsService.upNextKey,
        HomeWidgetsPayload.upNext(HomeWidgetsPayload.pickUpNext(tasks.todayPreviewTasks(), open), open: open.length),
      ));
    }
    final latest = HomeWidgetsPayload.latestOf(conversations.conversations);
    if (latest != null) {
      unawaited(service.publish(HomeWidgetsService.latestKey, HomeWidgetsPayload.latest(latest, l10n())));
    }
  }
}
