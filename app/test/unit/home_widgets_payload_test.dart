import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/home_widgets_service.dart';

/// What the iOS Home Screen widgets are given (ios/BatteryWidget/SharedDefaults.swift reads it).
void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  BtDevice device(String id, String name, DeviceType type) => BtDevice(id: id, name: name, type: type, rssi: -50);

  group('Devices', () {
    test('the connected wearable first, then the most recently paired; battery only where live', () {
      final omi = device('omi-1', 'Omi', DeviceType.omi);
      final plaud = device('plaud-1', 'PLAUD NotePin', DeviceType.plaud);
      final bee = device('bee-1', 'Bee', DeviceType.bee);
      final doc = HomeWidgetsPayload.devices(
        saved: [omi, plaud, bee], // paired in this order
        connected: plaud,
        isConnected: true,
        battery: 42,
        charging: true,
      );
      final devices = (doc['devices'] as List).cast<Map<String, Object?>>();
      expect(devices.map((d) => d['id']), ['plaud-1', 'bee-1', 'omi-1']);
      expect(devices.first, {
        'id': 'plaud-1',
        'name': 'PLAUD NotePin',
        'image': 'device-plaud',
        'connected': true,
        'battery': 42,
        'charging': true,
      });
      expect(devices[1]['connected'], false);
      expect(devices[1]['battery'], -1, reason: 'a device that is not connected has no live battery');
      expect(devices[2]['image'], 'pendant', reason: 'an Omi pendant is drawn as the orb');
    });

    test('nothing connected: every paired device, none live; the phone is never listed', () {
      final omi = device('omi-1', '', DeviceType.omi);
      final doc =
          HomeWidgetsPayload.devices(saved: [omi], connected: null, isConnected: false, battery: 80, charging: false);
      final devices = (doc['devices'] as List).cast<Map<String, Object?>>();
      expect(devices, hasLength(1));
      expect(devices.single['name'], 'Omi', reason: 'an unnamed pendant still has a name');
      expect(devices.single['connected'], false);
      expect(devices.single['battery'], -1);
    });

    test('each product has its own picture', () {
      expect(HomeWidgetsPayload.image(device('a', 'Watch', DeviceType.appleWatch)), 'device-apple-watch');
      expect(HomeWidgetsPayload.image(device('b', 'Limitless', DeviceType.limitless)), 'device-limitless');
      expect(HomeWidgetsPayload.image(device('c', 'Fieldy', DeviceType.fieldy)), 'device-fieldy');
      expect(HomeWidgetsPayload.image(device('d', 'Friend', DeviceType.friendPendant)), 'device-friend');
      expect(HomeWidgetsPayload.image(device('e', 'Ray-Ban', DeviceType.raybanMeta)), 'device-rayban');
      expect(HomeWidgetsPayload.image(device('f', 'Omi Glass', DeviceType.openglass)), 'device-glass');
    });
  });

  test('Up next: the first tasks with their due time, and how many are open', () {
    final due = DateTime.utc(2026, 9, 26, 21);
    final doc = HomeWidgetsPayload.upNext([
      ActionItemWithMetadata(id: 't1', description: ' Call Chitapa ', completed: false, dueAt: due),
      const ActionItemWithMetadata(id: 't2', description: 'Send the pricing draft', completed: false),
      const ActionItemWithMetadata(id: 't3', description: 'Third', completed: false),
      const ActionItemWithMetadata(id: 't4', description: 'Fourth', completed: false),
    ], open: 7);
    expect(doc['open'], 7);
    final tasks = (doc['tasks'] as List).cast<Map<String, Object?>>();
    expect(tasks.map((t) => t['id']), ['t1', 't2', 't3']);
    expect(tasks.first, {'id': 't1', 'title': 'Call Chitapa', 'due': due.millisecondsSinceEpoch / 1000});
    expect(tasks[1]['due'], isNull);
  });

  group('Latest', () {
    ServerConversation conversation(String id,
        {bool discarded = false, ConversationStatus? status, String title = ''}) {
      final structured = Structured(title, '')..actionItems = [ActionItem('Call back')];
      return ServerConversation(
        id: id,
        createdAt: DateTime.utc(2026, 9, 26, 19, 14),
        structured: structured,
        discarded: discarded,
        status: status ?? ConversationStatus.completed,
        startedAt: DateTime.utc(2026, 9, 26, 19, 14),
        finishedAt: DateTime.utc(2026, 9, 26, 19, 14, 14),
      );
    }

    test('the newest kept, finished conversation', () {
      final list = [
        conversation('live', status: ConversationStatus.in_progress),
        conversation('gone', discarded: true),
        conversation('kept', title: 'Call Chitapa reminder'),
      ];
      expect(HomeWidgetsPayload.latestOf(list)?.id, 'kept');
      expect(HomeWidgetsPayload.latestOf([conversation('gone', discarded: true)]), isNull);
    });

    test('its title, when it started, and "1 task · 14s" in the app\'s words', () {
      final doc = HomeWidgetsPayload.latest(conversation('kept', title: 'Call Chitapa reminder'), en)!;
      expect(doc['title'], 'Call Chitapa reminder');
      expect(doc['at'], DateTime.utc(2026, 9, 26, 19, 14).millisecondsSinceEpoch / 1000);
      expect(doc['detail'], startsWith('1 task · '));
      expect(HomeWidgetsPayload.latest(conversation('untitled'), en)!['title'], en.untitledConversation);
      expect(HomeWidgetsPayload.latest(null, en), isNull);
    });
  });
}
