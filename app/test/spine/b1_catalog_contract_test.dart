import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart';

void main() {
  test('B1 initial catalog controls cannot disappear or move between surfaces', () {
    final catalog = jsonDecode(addressableControlsJson) as Map<String, dynamic>;
    final required = <String, List<String>>{
      'chat': ['omi.chat.input', 'omi.chat.send'],
      'home': ['omi.home.tab_home', 'omi.home.tab_conversations', 'omi.home.tab_tasks'],
      'conversations': ['omi.conversations.row.rdaf2934440d6b578d73634beaa346288f9702bae8e7242ac870532b6ac43fb5c'],
      'conversation_detail': ['omi.conversation_detail.back', 'omi.conversation_detail.ask'],
      'memories': ['omi.memories.create'],
      'tasks': ['omi.tasks.create'],
      'settings': ['omi.settings.profile', 'omi.settings.done'],
      'onboarding': ['omi.onboarding.google'],
      'devices': ['omi.devices.back', 'omi.devices.guide'],
    };
    for (final entry in required.entries) {
      expect((catalog[entry.key] as List).map((c) => c['key']), containsAll(entry.value));
    }
  });
}
