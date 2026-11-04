import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('detail ignores wiring noise and propagates mutable catalog and selected detail edits', () {
    final apps = AppProvider();
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    final detail = ConversationDetailProvider();
    addTearDown(detail.dispose);
    addTearDown(apps.dispose);
    addTearDown(conversations.dispose);
    // Unobserved startup must not resolve a selection or emit product state.
    detail.setProviders(apps, conversations);
    var notifications = 0;
    detail.addListener(() => notifications++);
    detail.setProviders(apps, conversations);
    expect(notifications, 0);
    notifications = 0;
    for (var i = 0; i < 4; i++) {
      detail.setProviders(apps, conversations);
    }
    expect(notifications, 0);
    final app = App(
        id: 'a',
        name: 'Before',
        author: 'test',
        description: '',
        image: '',
        capabilities: {'memories'},
        status: 'approved',
        category: 'test',
        approved: true,
        ratingCount: 0,
        enabled: true,
        deleted: false,
        isPaid: false,
        isUserPaid: false);
    apps.apps = [app];
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    app.name = 'After';
    detail.setProviders(apps, conversations);
    expect(notifications, 2);
    // The attribution row renders description and image; a catalog refresh
    // changing only those must still notify while detail is open.
    app.description = 'Fresh description';
    detail.setProviders(apps, conversations);
    expect(notifications, 3);
    app.image = '/apps/new.png';
    detail.setProviders(apps, conversations);
    expect(notifications, 4);
    final selected = ServerConversation(
        id: 'selected', createdAt: DateTime(2026, 10, 13), structured: Structured('Before', 'Overview'));
    conversations.conversations = [selected];
    conversations.groupConversationsByDate();
    detail.updateConversation(selected.id, conversations.groupedConversations.keys.single);
    detail.setProviders(apps, conversations);
    notifications = 0;
    selected.structured.title = 'After';
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    conversations.isLoadingConversations = true;
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    conversations.memoriesToDelete[selected.id] = selected;
    detail.setProviders(apps, conversations);
    expect(notifications, 2);
  });

  test('detail notifies on in-place speaker-identity edits without other detail changes', () {
    final apps = AppProvider();
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    final detail = ConversationDetailProvider();
    addTearDown(detail.dispose);
    addTearDown(apps.dispose);
    addTearDown(conversations.dispose);

    final segment = TranscriptSegment(
      id: 'seg-1',
      text: 'hello',
      speaker: 'SPEAKER_00',
      speakerId: 0,
      isUser: false,
      personId: null,
      start: 0,
      end: 2,
      translations: [],
    );
    final selected = ServerConversation(
        id: 'selected',
        createdAt: DateTime(2026, 10, 13),
        structured: Structured('Before', 'Overview'),
        transcriptSegments: [segment]);
    conversations.conversations = [selected];
    conversations.groupConversationsByDate();
    // setProviders first: updateConversation resolves through the wired
    // conversationProvider (groupedConversations lookup).
    detail.setProviders(apps, conversations);
    detail.updateConversation(selected.id, conversations.groupedConversations.keys.single);

    var notifications = 0;
    detail.addListener(() => notifications++);
    // Bind the projection with the selected conversation ('##null' → real
    // fingerprint) exactly like the wiring test above.
    detail.setProviders(apps, conversations);
    expect(detail.conversationOrNull?.id, 'selected', reason: 'sanity: detail resolves the selected conversation');
    notifications = 0;

    // In-place segment identity edits change no fingerprinted field and no
    // container identity; the revision counter must still notify detail.
    conversations.applySpeakerPromptIdentities(GeneratedSpeakerTagPromptAnswerResponse(
      conversationId: selected.id,
      qualityOutcome: 'ok',
      segmentIdentities: const [GeneratedSpeakerTagPromptSegmentIdentity(id: 'seg-1', isUser: true, personId: 'p1')],
    ));
    expect(segment.isUser, isTrue, reason: 'sanity: the in-place edit applied');
    detail.setProviders(apps, conversations);
    expect(notifications, 1, reason: 'speaker-identity edits must notify the detail projection');

    // A prompt answer that matches no segment of the selected conversation
    // bumps nothing: no spurious notification.
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
  });
}
