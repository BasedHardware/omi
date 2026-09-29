import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/pages/onboarding/guided_voice_io.dart';
import 'package:omi/services/siri_integration.dart';

class _MemoryHost extends SiriIndexApi {
  final rows = <String, SiriMemory>{};

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> memories) async {
    for (final row in memories) {
      rows[row.id] = row;
    }
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'guided-owner'});
    await SharedPreferencesUtil.init();
  });

  test('confirmed guided onboarding memory reaches the Siri snapshot', () async {
    final host = _MemoryHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'guided-owner');
    addTearDown(() => SiriIntegration.testInstance = null);
    final memory = Memory(
        id: 'guided-1',
        uid: 'guided-owner',
        content: 'I like coffee',
        category: MemoryCategory.system,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private);
    final io = DeviceGuidedVoiceIO(createMemoryRequest: (_, __, ___) async => memory);

    expect(await io.remember('I like coffee'), isTrue);
    await SiriIntegration.current.drainIndexForTest();
    expect(host.rows['guided-1']?.content, 'I like coffee');
  });
}
