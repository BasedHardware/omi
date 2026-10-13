import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  ServerConversation row(String id, {required bool discarded}) {
    return ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 1, 1),
      structured: Structured('Title', ''),
      status: ConversationStatus.completed,
      discarded: discarded,
    );
  }

  test('a discarded-only list is explained once and a later real conversation clears it', () async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);

    expect(provider.claimDiscardedOnlyExplanation(), DiscardedOnlyClaim.notDiscardedOnly);
    await provider.addConversation(row('gone', discarded: true));
    expect(provider.claimDiscardedOnlyExplanation(), DiscardedOnlyClaim.shown);
    expect(provider.homeEmptyExplanation, HomeEmptyExplanation.discardedOnly);
    expect(provider.claimDiscardedOnlyExplanation(), DiscardedOnlyClaim.alreadyShown);

    await provider.addConversation(row('kept', discarded: false));
    provider.showEmptyRecordingExplanation();
    expect(provider.homeEmptyExplanation, HomeEmptyExplanation.discardedOnly);
    provider.clearEmptyRecordingExplanation();
    expect(provider.homeEmptyExplanation, HomeEmptyExplanation.none);
  });

  test('an empty list can show the too-short explanation until a conversation arrives', () {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    provider.showEmptyRecordingExplanation();
    expect(provider.homeEmptyExplanation, HomeEmptyExplanation.tooShort);
    provider.upsertConversation(row('kept', discarded: false));
    expect(provider.homeEmptyExplanation, HomeEmptyExplanation.none);
  });
}
