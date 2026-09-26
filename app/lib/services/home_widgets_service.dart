import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_duration.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/extensions/string.dart';

/// What the iOS Home Screen widgets show, as the JSON documents the widget extension reads
/// (ios/BatteryWidget/SharedDefaults.swift): the reader's wearables, the next open tasks and the
/// latest conversation. Pure, so each document can be checked without a phone.
abstract final class HomeWidgetsPayload {
  /// The picture the widget draws for [device]: "pendant" for an Omi pendant (the widget draws
  /// the orb), otherwise the product photo in the widget's assets.
  static String image(BtDevice device) {
    final path = DeviceUtils.getDeviceImageFromBtDevice(device);
    final pictures = {
      Assets.images.appleWatch.path: 'device-apple-watch',
      Assets.images.beeDevice.path: 'device-bee',
      Assets.images.friendPendant.path: 'device-friend',
      Assets.images.omiDevkitWithoutRope.path: 'device-devkit',
      Assets.images.omiGlass.path: 'device-glass',
      Assets.images.plaudNotePin.path: 'device-plaud',
      Assets.images.raybanMeta.path: 'device-rayban',
      Assets.images.limitless.path: 'device-limitless',
      Assets.images.fieldy.path: 'device-fieldy',
      Assets.images.neoOne.path: 'device-neo',
    };
    return pictures[path] ?? 'pendant';
  }

  /// The wearables the Devices widget pages through: the connected one first, then the most
  /// recently paired. Only the connected one has a live battery. The phone is never a device.
  static Map<String, Object?> devices({
    required List<BtDevice> saved,
    required BtDevice? connected,
    required bool isConnected,
    required int battery,
    required bool charging,
  }) {
    final ordered = <String, BtDevice>{};
    final live = isConnected && connected != null && connected.id.isNotEmpty ? connected : null;
    if (live != null) ordered[live.id] = live;
    for (final device in saved.reversed) {
      if (device.id.isNotEmpty) ordered.putIfAbsent(device.id, () => device);
    }
    return {
      'devices': [
        for (final device in ordered.values)
          {
            'id': device.id,
            'name': device.name.trim().isEmpty ? 'Omi' : device.name.trim(),
            'image': image(device),
            'connected': device.id == live?.id,
            'battery': device.id == live?.id && battery >= 0 ? battery.clamp(0, 100) : -1,
            'charging': device.id == live?.id && charging,
          },
      ],
    };
  }

  /// The tasks Up next shows: today's first, then the other open ones soonest due first (undated
  /// last), so what is coming shows ahead of its day (#5080).
  static List<ActionItemWithMetadata> pickUpNext(
    List<ActionItemWithMetadata> today,
    List<ActionItemWithMetadata> open, {
    int limit = 3,
  }) {
    final rest = open.where((task) => today.every((d) => d.id != task.id)).toList();
    // Stable: tasks without a due date keep the order the list gave them.
    final dated = rest.where((task) => task.dueAt != null).toList()..sort((a, b) => a.dueAt!.compareTo(b.dueAt!));
    return [...today, ...dated, ...rest.where((task) => task.dueAt == null)].take(limit).toList();
  }

  /// Up next: the tasks [pickUpNext] chose (at most [limit]) with when each is due, and how many
  /// are open in all.
  static Map<String, Object?> upNext(List<ActionItemWithMetadata> tasks, {required int open, int limit = 3}) {
    return {
      'tasks': [
        for (final task in tasks.take(limit))
          {
            'id': task.id,
            'title': task.description.trim(),
            'due': task.dueAt == null ? null : task.dueAt!.millisecondsSinceEpoch / 1000,
          },
      ],
      'open': open,
    };
  }

  /// The newest finished conversation that was kept (not discarded), or null when there is none.
  static ServerConversation? latestOf(List<ServerConversation> conversations) {
    for (final conversation in conversations) {
      if (conversation.discarded || conversation.deleted) continue;
      if (conversation.status != ConversationStatus.completed) continue;
      return conversation;
    }
    return null;
  }

  /// Latest: its title, when it started, and "1 task · 14 s" in the app's words.
  static Map<String, Object?>? latest(ServerConversation? conversation, AppLocalizations l10n) {
    if (conversation == null) return null;
    final title = conversation.structured.title.decodeString.trim();
    final tasks = conversation.structured.actionItems.where((item) => !item.deleted).length;
    final seconds = conversation.getDurationInSeconds();
    return {
      'id': conversation.id,
      'title': title.isEmpty ? l10n.untitledConversation : title,
      'at': (conversation.startedAt ?? conversation.createdAt).millisecondsSinceEpoch / 1000,
      'detail': [
        if (tasks > 0) l10n.tasksCountLabel(tasks),
        if (seconds > 0) OmiDuration.compact(seconds, l10n),
      ].join(' · '),
    };
  }
}

/// Writes the widget documents to the App Group through the battery widget's channel, only when
/// one changed, and asks iOS to redraw that widget. Nothing happens off iOS.
class HomeWidgetsService {
  HomeWidgetsService._();

  static final HomeWidgetsService instance = HomeWidgetsService._();

  static const MethodChannel _channel = MethodChannel('com.omi.battery_widget');

  static const String devicesKey = 'widget_devices';
  static const String upNextKey = 'widget_up_next';
  static const String latestKey = 'widget_latest';

  final Map<String, String?> _published = {};

  /// Publishes [document] under [key]; null clears it (the widget then asks to open Omi).
  Future<void> publish(String key, Map<String, Object?>? document) async {
    if (!Platform.isIOS) return;
    final json = document == null ? null : jsonEncode(document);
    if (_published.containsKey(key) && _published[key] == json) return;
    _published[key] = json;
    try {
      await _channel.invokeMethod('updateWidgetData', {'key': key, 'json': json});
    } catch (e) {
      _published.remove(key);
      Logger.debug('HomeWidgetsService.publish($key) failed: $e');
    }
  }

  /// Signing out: no tasks or conversation titles stay on the Home Screen.
  Future<void> clear() async {
    await Future.wait([publish(upNextKey, null), publish(latestKey, null), publish(devicesKey, null)]);
  }
}
