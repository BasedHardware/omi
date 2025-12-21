import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/services/app_review_service.dart';

class ConversationProvider extends ChangeNotifier {
  List<ServerConversation> conversations = [];
  List<ServerConversation> searchedConversations = [];
  Map<DateTime, List<ServerConversation>> groupedConversations = {};

  // Get filtered conversations as a flat list (matching what's displayed in the UI)
  List<ServerConversation> get filteredConversations {
    return groupedConversations.values.expand((list) => list).toList();
  }

  bool isLoadingConversations = false;
  bool showDiscardedConversations = false;
  bool showShortConversations = false;
  int shortConversationThreshold = 60; // in seconds
  bool showStarredOnly = false; // filter to show only starred conversations
  DateTime? selectedDate;

  String previousQuery = '';
  int totalSearchPages = 1;
  int currentSearchPage = 1;

  Timer? _processingConversationWatchTimer;

  // Add debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 60); // Minimum time between refreshes

  List<ServerConversation> processingConversations = [];

  // Merge functionality state
  Set<String> mergingConversationIds = {};
  bool isSelectionModeActive = false;
  Set<String> selectedConversationIds = {};
  StreamSubscription<MergeCompletedEvent>? _mergeCompletedSubscription;

  final AppReviewService _appReviewService = AppReviewService();

  bool isFetchingConversations = false;

  ConversationProvider() {
    _setupMergeListener();
    _preload();
  }

  _preload() async {
    if (DevConstants.useMockData) {
      _loadMockConversations();
    }
  }

  void _loadMockConversations() {
    conversations = [
      // Mock Conversation 1: Casual tech + work chatter
      ServerConversation(
        id: 'mock-1',
        createdAt: DateTime.now().subtract(const Duration(hours: 3)),
        startedAt: DateTime.now().subtract(const Duration(hours: 3, minutes: 20)),
        finishedAt: DateTime.now().subtract(const Duration(hours: 3, minutes: 4)),
        structured: Structured(
          'Casual Tech Troubles and Work Chit-Chat',
          'Tech issue and apps\n• Play Store downloaded, then stopped working\n• Suggested to check device settings and storage\n\nFood and small talk\n• Mentioned chicken, cream, paneer dishes\n• Commented that the food was quite nice\n\nSchedule and meeting changes\n• Original time around 1, then schedule changed\n• Asked if updated schedule on Discord was seen\n\nWork, proof, and metrics\n• Amazon website metrics mentioned as important\n• Need proof of work before processing or merging\n• Diarization contribution improves chances significantly\n\nPlugins and laptop\n• Asked about adding Dart plugin in settings\n• Questioned how old the laptop is\n\nResponsibility and people\n• Noted others are consistent, hardworking, sometimes sad\n• Responsibility is shared; not solely yours\n\nNext steps\n• Check storage/settings to fix the Play Store issue\n• Confirm new schedule on Discord and prepare proof-of-work artifacts',
          emoji: '💼',
          category: 'work',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's1',
            text:
                'I downloaded from the Play Store but the app just stopped working. Maybe I should check device settings and free up storage.',
            speaker: 'SPEAKER_00',
            isUser: false,
            personId: null,
            start: 0.0,
            end: 8.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's2',
            text: 'Also, we changed the schedule after the first plan around 1. Did you see the updated Discord post?',
            speaker: 'SPEAKER_01',
            isUser: true,
            personId: null,
            start: 8.5,
            end: 14.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's3',
            text: 'We talked about chicken with cream and paneer dishes yesterday. The food was actually quite nice.',
            speaker: 'SPEAKER_00',
            isUser: false,
            personId: null,
            start: 14.5,
            end: 22.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's4',
            text: 'For proof of work, we need clear metrics on Amazon before we process or merge anything. Diarization improvements will help our chances.',
            speaker: 'SPEAKER_01',
            isUser: true,
            personId: null,
            start: 23.0,
            end: 32.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's5',
            text: 'Can we add the Dart plugin in settings? By the way, how old is this laptop? It might explain some issues.',
            speaker: 'SPEAKER_00',
            isUser: false,
            personId: null,
            start: 32.5,
            end: 40.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's6',
            text:
                'Everyone here is consistent and hardworking, even when they are sad. Responsibility is shared; it is not just your burden.',
            speaker: 'SPEAKER_01',
            isUser: true,
            personId: null,
            start: 40.5,
            end: 49.0,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 2: Flutter iOS setup troubleshooting
      ServerConversation(
        id: 'mock-2',
        createdAt: DateTime.now().subtract(const Duration(days: 1, hours: 2)),
        startedAt: DateTime.now().subtract(const Duration(days: 1, hours: 2, minutes: 15)),
        finishedAt: DateTime.now().subtract(const Duration(days: 1, hours: 2, minutes: 2)),
        structured: Structured(
          'Developers Troubleshoot Flutter iOS Setup',
          'Flutter app setup and run time\n• Flutter app run taking unusually long\n• First run after Flutter upgrade known to be slower\n• Cloned project and triggered run from terminal\n\nFlutter upgrade impact\n• Flutter upgrade caused extra setup time\n• Tooling likely doing one-time build/configuration\n• Delay expected mainly on first app execution\n\niOS vs Android and simulator issue\n• User wishes they had an Android device\n• iOS-specific issue mentioned for current setup\n• iOS simulator not detecting connected iPhone as usual\n\nEnvironment and connectivity\n• Multiple laptops present; one seat reserved\n• Request made to connect to free Wi‑Fi\n\nNext steps\n• Wait longer for first Flutter run to complete\n• Troubleshoot iPhone detection in iOS simulator\n• Connect to Wi‑Fi and retry the build',
          emoji: '🛠️',
          category: 'work',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's4',
            text: 'The Flutter app run is taking unusually long after the upgrade. The first run is always slower.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 7.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's5',
            text: 'We cloned the project and are running from terminal. The toolchain is probably doing a one-time build and configuration.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.5,
            end: 16.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's6',
            text: 'I wish I had an Android device here. The iOS simulator is not detecting the connected iPhone.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 16.5,
            end: 24.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's7',
            text: 'There are multiple laptops around; one seat was reserved. Let’s also request to connect to free Wi‑Fi.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 24.5,
            end: 31.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's8',
            text: 'Next steps: wait for the first run to finish, troubleshoot the iPhone detection in the simulator, and reconnect Wi‑Fi if needed.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 32.0,
            end: 41.0,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 3: Follow-up metrics and planning chat
      ServerConversation(
        id: 'mock-3',
        createdAt: DateTime.now().subtract(const Duration(days: 2, hours: 5)),
        startedAt: DateTime.now().subtract(const Duration(days: 2, hours: 5, minutes: 10)),
        finishedAt: DateTime.now().subtract(const Duration(days: 2, hours: 4, minutes: 50)),
        structured: Structured(
          'Metrics Proof and Schedule Shuffle',
          'Proof and metrics\n• Need proof of work before processing or merging\n• Amazon website metrics stressed as critical\n• Diarization contribution improves approval chances\n\nSchedule and comms\n• Revisited schedule shift from original 1 o’clock slot\n• Asked if the updated Discord schedule was seen\n\nLight chatter and tools\n• Follow-up on chicken/paneer meal that went well\n• Suggested enabling Dart plugin in settings\n\nAction items\n• Prepare proof artifacts and updated metrics\n• Confirm schedule in Discord and share updates\n• Keep diarization improvements moving to strengthen review',
          emoji: '📊',
          category: 'work',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's6',
            text: 'Before processing or merging, we need clear proof-of-work. Amazon metrics are important for this push.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 7.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's7',
            text: 'Did you see the updated schedule on Discord? Original time was around 1, then it shifted again.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.5,
            end: 14.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's8',
            text: 'We were still talking about the chicken and paneer meal; it turned out pretty good.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 14.5,
            end: 19.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's9',
            text: 'If we keep improving diarization, it will significantly improve our approval chances.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 20.0,
            end: 26.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's10',
            text: 'Let’s also make sure the Dart plugin is set up; it might unblock some of the debugging.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 26.5,
            end: 32.0,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 4: Async API integration and blockers
      ServerConversation(
        id: 'mock-4',
        createdAt: DateTime.now().subtract(const Duration(days: 3, hours: 1)),
        startedAt: DateTime.now().subtract(const Duration(days: 3, hours: 1, minutes: 15)),
        finishedAt: DateTime.now().subtract(const Duration(days: 3, hours: 1, minutes: 0)),
        structured: Structured(
          'Async API Integration and Blockers',
          'API performance\n• New async client added; initial requests still slow\n• Suspect cold-starts and missing caching headers\n\nAuth and tokens\n• Discussed short-lived tokens failing mid-call\n• Proposed refresh hook or retry with backoff\n\nDebugging and logs\n• Need more verbose logs on 429/500 responses\n• Add request IDs to correlate across services\n\nNext steps\n• Enable caching for read endpoints\n• Implement token refresh and backoff\n• Add structured logs with request IDs',
          emoji: '🔧',
          category: 'work',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's11',
            text: 'The new async client is in, but first calls are still slow. Might be cold-starts plus missing cache headers.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 7.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's12',
            text: 'Tokens are short-lived and sometimes expire mid-call. We should refresh or retry with backoff.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.5,
            end: 14.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's13',
            text: 'Let’s turn on verbose logging and include request IDs so we can trace the 429s and 500s.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 14.5,
            end: 21.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's14',
            text: 'Next: cache the read endpoints, add refresh hooks, and backoff retries for the noisy endpoints.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 21.5,
            end: 28.0,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 5: Personal weekend planning and errands
      ServerConversation(
        id: 'mock-5',
        createdAt: DateTime.now().subtract(const Duration(days: 4, hours: 2)),
        startedAt: DateTime.now().subtract(const Duration(days: 4, hours: 2, minutes: 10)),
        finishedAt: DateTime.now().subtract(const Duration(days: 4, hours: 1, minutes: 50)),
        structured: Structured(
          'Weekend Plans and Errands',
          'Groceries and cooking\n• Planning to cook pasta and buy fresh veggies\n• Debating which sauce to use and budget for groceries\n\nSocial plans\n• Meetup with friends at the park; backup cafe if it rains\n• Quick check on shared calendar for timing conflicts\n\nTasks and reminders\n• Need to return an online order before deadline\n• Set reminder to pick up dry cleaning and charge bike\n\nBudget and timing\n• Estimating costs and time for all errands\n• Want to finish before evening meetup',
          emoji: '🧺',
          category: 'personal',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's15',
            text: 'I want to cook pasta this weekend and grab fresh veggies. Still deciding which sauce and budget.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 7.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's16',
            text: 'Let’s meet at the park unless it rains—then the cafe. I’ll check the shared calendar for conflicts.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.5,
            end: 14.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's17',
            text: 'I must return that online order before the deadline and pick up dry cleaning. Also need to charge the bike.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 15.0,
            end: 22.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's18',
            text: 'If we finish errands by evening, we can still make the meetup on time.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 22.5,
            end: 27.5,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 6: Design review and user feedback
      ServerConversation(
        id: 'mock-6',
        createdAt: DateTime.now().subtract(const Duration(days: 5)),
        startedAt: DateTime.now().subtract(const Duration(days: 5, minutes: 40)),
        finishedAt: DateTime.now().subtract(const Duration(days: 5, minutes: 15)),
        structured: Structured(
          'Design Review and User Feedback',
          'Navigation and layout\n• Sidebar feels heavy; consider lighter variant\n• Primary CTA needs stronger contrast\n\nUser feedback\n• Users liked faster load; still confused by filters\n• Mobile users want larger tap targets\n\nContent clarity\n• Tooltips/help text requested near advanced settings\n• Suggested shorter empty-state copy and an example\n\nAction items\n• Explore lighter sidebar and bolder CTA style\n• Improve filter UX and tap targets on mobile\n• Add concise tooltips and better empty states',
          emoji: '🎨',
          category: 'work',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's19',
            text: 'The sidebar feels heavy. We should try a lighter variant and boost contrast on the primary CTA.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 7.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's20',
            text: 'Users liked the faster load but are still confused by filters. Mobile folks want bigger tap targets.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.5,
            end: 14.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's21',
            text: 'Add tooltips near advanced settings, and tighten the empty-state copy with an example.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 14.5,
            end: 20.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's22',
            text: 'Next: lighter sidebar, bolder CTA, better filters, tap targets, and concise tooltips.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 21.0,
            end: 27.0,
            translations: [],
          ),
        ],
      ),
      // Mock Conversation 7: Health check-in and routine tweaks
      ServerConversation(
        id: 'mock-7',
        createdAt: DateTime.now().subtract(const Duration(days: 6, hours: 3)),
        startedAt: DateTime.now().subtract(const Duration(days: 6, hours: 3, minutes: 30)),
        finishedAt: DateTime.now().subtract(const Duration(days: 6, hours: 3, minutes: 5)),
        structured: Structured(
          'Health Check-In and Routine Tweaks',
          'Sleep and energy\n• Slept 6 hours; felt groggy in the morning\n• Wants to target 7.5–8 hours consistently\n\nExercise and movement\n• Quick walk planned after lunch\n• Considering adding two strength sessions weekly\n\nFood and hydration\n• Aiming for lighter dinners and more water\n• Tracking caffeine to avoid late-day spikes\n\nNext steps\n• Set bedtime reminder and morning stretch routine\n• Schedule two short workouts into the calendar\n• Keep a simple log for sleep and caffeine',
          emoji: '🧘',
          category: 'health',
        ),
        transcriptSegments: [
          TranscriptSegment(
            id: 's23',
            text: 'I only slept about 6 hours and felt groggy. Want to hit 7.5 to 8 hours consistently.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0.0,
            end: 6.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's24',
            text: 'Planning a quick walk after lunch and maybe two strength sessions each week.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 7.0,
            end: 12.5,
            translations: [],
          ),
          TranscriptSegment(
            id: 's25',
            text: 'I’ll aim for lighter dinners, more water, and track caffeine so it doesn’t spike late.',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 13.0,
            end: 19.0,
            translations: [],
          ),
          TranscriptSegment(
            id: 's26',
            text: 'Let’s add a bedtime reminder, morning stretches, and put two workouts on the calendar.',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: 19.5,
            end: 25.0,
            translations: [],
          ),
        ],
      ),
    ];

    // IMPORTANT: Group conversations by date so they appear in the UI
    // The ConversationsPage reads from groupedConversations (not conversations directly)
    // Without this, the list will show "No conversations yet" even though conversations exist
    groupConversationsByDate();

    notifyListeners();
  }

  void _setupMergeListener() {
    _mergeCompletedSubscription = MergeNotificationHandler.onMergeCompleted.listen((event) {
      onMergeCompleted(event.mergedConversationId, event.removedConversationIds);
    });
  }

  void resetGroupedConvos() {
    groupConversationsByDate();
  }

  Future updateSearchedConvoDetails(String id, DateTime date, int idx) async {
    var convo = await getConversationById(id);
    if (convo != null) {
      updateSpecificGroupedConvo(convo, date, idx);
    }
    notifyListeners();
  }

  void updateSpecificGroupedConvo(ServerConversation convo, DateTime date, int idx) {
    groupedConversations[date]![idx] = convo;
    notifyListeners();
  }

  Future<void> searchConversations(String query, {bool showShimmer = false}) async {
    if (query.isEmpty) {
      previousQuery = "";
      currentSearchPage = 0;
      totalSearchPages = 0;
      searchedConversations = [];
      groupConversationsByDate();
      return;
    }

    if (showShimmer) {
      setLoadingConversations(true);
    } else {
      setIsFetchingConversations(true);
    }

    previousQuery = query;
    var (convos, current, total) = await searchConversationsServer(query, includeDiscarded: showDiscardedConversations);
    convos.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    searchedConversations = convos;
    currentSearchPage = current;
    totalSearchPages = total;
    groupSearchConvosByDate();

    if (showShimmer) {
      setLoadingConversations(false);
    } else {
      setIsFetchingConversations(false);
    }

    notifyListeners();
  }

  Future<void> searchMoreConversations() async {
    if (totalSearchPages < currentSearchPage + 1) {
      return;
    }
    setLoadingConversations(true);
    var (newConvos, current, total) = await searchConversationsServer(
      previousQuery,
      page: currentSearchPage + 1,
      includeDiscarded: showDiscardedConversations,
    );
    searchedConversations.addAll(newConvos);
    searchedConversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    totalSearchPages = total;
    currentSearchPage = current;
    groupSearchConvosByDate();
    setLoadingConversations(false);
    notifyListeners();
  }

  int groupedSearchConvoIndex(ServerConversation convo) {
    var convoDate = convo.startedAt ?? convo.createdAt;
    var date = DateTime(convoDate.year, convoDate.month, convoDate.day);
    if (groupedConversations.containsKey(date)) {
      return groupedConversations[date]!.indexWhere((element) => element.id == convo.id);
    }
    return -1;
  }

  void addProcessingConversation(ServerConversation conversation) {
    processingConversations.add(conversation);
    notifyListeners();
  }

  void removeProcessingConversation(String conversationId) {
    processingConversations.removeWhere((m) => m.id == conversationId);
    notifyListeners();
  }

  void onConversationTap(int idx) {
    if (idx < 0 || idx > conversations.length - 1) {
      return;
    }
    var changed = false;
    if (conversations[idx].isNew) {
      conversations[idx].isNew = false;
      changed = true;
    }
    if (changed) {
      groupConversationsByDate();
    }
  }

  void toggleDiscardConversations() {
    showDiscardedConversations = !showDiscardedConversations;
    SharedPreferencesUtil().showDiscardedMemories = showDiscardedConversations;

    // Clear grouped conversations to show shimmer effect while loading
    groupedConversations = {};
    notifyListeners();

    if (previousQuery.isNotEmpty) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }

    MixpanelManager().showDiscardedMemoriesToggled(showDiscardedConversations);
  }

  void toggleShortConversations() {
    showShortConversations = !showShortConversations;
    SharedPreferencesUtil().showShortConversations = showShortConversations;

    // Clear and refresh to reflect the change
    groupedConversations = {};
    notifyListeners();

    if (previousQuery.isNotEmpty) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }
  }

  void setShortConversationThreshold(int seconds) {
    shortConversationThreshold = seconds;
    SharedPreferencesUtil().shortConversationThreshold = seconds;

    // Clear and refresh to reflect the change
    groupedConversations = {};
    notifyListeners();

    if (previousQuery.isNotEmpty) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }
  }

  void toggleStarredFilter() {
    showStarredOnly = !showStarredOnly;
    groupConversationsByDate();
    notifyListeners();
  }

  void setLoadingConversations(bool value) {
    isLoadingConversations = value;
    notifyListeners();
  }

  Future refreshConversations() async {
    // MOCK DATA FIX: Skip refresh when using mock data to prevent API calls from wiping it out
    if (DevConstants.useMockData) {
      return;
    }

    // Debounce mechanism: only refresh if enough time has passed since last refresh
    final now = DateTime.now();
    if (_lastRefreshTime != null && now.difference(_lastRefreshTime!) < _refreshCooldown) {
      debugPrint(
          'Skipping conversations refresh - too soon since last refresh (${now.difference(_lastRefreshTime!).inSeconds}s ago)');
      return;
    }

    // Cancel any pending refresh
    _refreshDebounceTimer?.cancel();

    // Set debounce timer
    _refreshDebounceTimer = Timer(const Duration(milliseconds: 500), () {
      _lastRefreshTime = DateTime.now();
      _fetchNewConversations();
    });
  }

  // Force refresh bypassing debounce (for manual refresh, connection restored, etc.)
  Future forceRefreshConversations() async {
    // MOCK DATA FIX: Skip refresh when using mock data to prevent API calls from wiping it out
    if (DevConstants.useMockData) {
      return;
    }

    _refreshDebounceTimer?.cancel();
    _lastRefreshTime = DateTime.now();
    await _fetchNewConversations();
  }

  Future _fetchNewConversations() async {
    setLoadingConversations(true);
    List<ServerConversation> newConversations = await _getConversationsFromServer();
    setLoadingConversations(false);

    List<ServerConversation> upsertConvos = [];

    // processing convos
    upsertConvos = newConversations
        .where((c) =>
            c.status == ConversationStatus.processing &&
            processingConversations.indexWhere((cc) => cc.id == c.id) == -1)
        .toList();
    if (upsertConvos.isNotEmpty) {
      processingConversations.insertAll(0, upsertConvos);
    }

    // completed convos
    upsertConvos = newConversations
        .where((c) => c.status == ConversationStatus.completed && conversations.indexWhere((cc) => cc.id == c.id) == -1)
        .toList();
    if (upsertConvos.isNotEmpty) {
      // Check if this is the first conversation
      bool wasEmpty = conversations.isEmpty;

      conversations.insertAll(0, upsertConvos);

      // Mark first conversation for app review
      if (wasEmpty && await _appReviewService.isFirstConversation()) {
        await _appReviewService.markFirstConversation();
      }
    }

    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  Future fetchConversations() async {
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    setLoadingConversations(true);
    conversations = await _getConversationsFromServer();
    setLoadingConversations(false);

    // processing convos
    processingConversations = conversations.where((m) => m.status == ConversationStatus.processing).toList();

    // completed convos
    conversations = conversations.where((m) => m.status == ConversationStatus.completed).toList();
    if (conversations.isEmpty) {
      conversations = SharedPreferencesUtil().cachedConversations;
    } else {
      SharedPreferencesUtil().cachedConversations = conversations;
    }
    if (searchedConversations.isEmpty) {
      searchedConversations = conversations;
    }
    _groupConversationsByDateWithoutNotify();

    notifyListeners();
  }

  Future getInitialConversations() async {
    // MOCK DATA FIX: When using mock data, skip the API call
    // fetchConversations() calls the server and overwrites the mock conversations
    // loaded in _preload() with an empty response from the API
    // This check ensures mock data persists and displays in the UI
    if (DevConstants.useMockData) {
      // Mock data already loaded in constructor via _preload() -> _loadMockConversations()
      // No need to fetch from server - just return early
      return;
    }

    // Production mode: fetch real conversations from the server
    await fetchConversations();
  }

  List<ServerConversation> _filterOutConvos(List<ServerConversation> convos) {
    return convos.where((convo) {
      // Filter by discarded status
      // When showDiscardedConversations is true, show all conversations (including discarded)
      // When showDiscardedConversations is false, hide discarded conversations
      if (!showDiscardedConversations && convo.discarded) {
        return false;
      }

      // Filter out short conversations unless explicitly showing them
      if (!showShortConversations) {
        final durationSeconds = convo.getDurationInSeconds();
        if (durationSeconds < shortConversationThreshold) {
          return false;
        }
      }

      // Filter by starred status if enabled
      if (showStarredOnly) {
        if (!convo.starred) {
          return false;
        }
      }

      // Apply date filter if selected
      if (selectedDate != null) {
        var effectiveDate = convo.startedAt ?? convo.createdAt;
        var convoDate = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
        var filterDate = DateTime(selectedDate!.year, selectedDate!.month, selectedDate!.day);
        if (convoDate != filterDate) {
          return false;
        }
      }
      return true;
    }).toList();
  }

  /// Filter conversations by a specific date
  Future<void> filterConversationsByDate(DateTime date) async {
    selectedDate = date;

    // Clear search when applying date filter
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  /// Clear the date filter
  Future<void> clearDateFilter() async {
    selectedDate = null;

    // Clear search when clearing date filter
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  void _groupSearchConvosByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(searchedConversations)) {
      var effectiveDate = conversation.startedAt ?? conversation.createdAt;
      var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    }
  }

  void _groupConversationsByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(conversations)) {
      var effectiveDate = conversation.startedAt ?? conversation.createdAt;
      var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    }
  }

  void groupConversationsByDate() {
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  void groupSearchConvosByDate() {
    _groupSearchConvosByDateWithoutNotify();
    notifyListeners();
  }

  (DateTime?, DateTime?) _getDateFilterRange() {
    if (selectedDate == null) return (null, null);
    final date = selectedDate!;
    return (
      DateTime(date.year, date.month, date.day, 0, 0, 0),
      DateTime(date.year, date.month, date.day, 23, 59, 59),
    );
  }

  Future _getConversationsFromServer() async {
    final (startDate, endDate) = _getDateFilterRange();

    return await getConversations(
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
    );
  }

  void updateActionItemState(String convoId, bool state, int i, DateTime date) {
    conversations.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed = state;
    groupedConversations[date]!.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed =
        state;
    notifyListeners();
  }

  Future getMoreConversationsFromServer() async {
    if (conversations.length % 50 != 0) return;
    if (isLoadingConversations) return;
    setLoadingConversations(true);

    // Date filter if selected
    final (startDate, endDate) = _getDateFilterRange();

    var newConversations = await getConversations(
      offset: conversations.length,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
    );
    conversations.addAll(newConversations);
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    _groupConversationsByDateWithoutNotify();
    setLoadingConversations(false);
    notifyListeners();
  }

  Future<void> addConversation(ServerConversation conversation) async {
    // Check if this is the first conversation
    bool wasEmpty = conversations.isEmpty;

    conversations.insert(0, conversation);
    _groupConversationsByDateWithoutNotify();

    // Mark first conversation for app review
    if (wasEmpty && await _appReviewService.isFirstConversation()) {
      await _appReviewService.markFirstConversation();
    }

    notifyListeners();
  }

  void upsertConversation(ServerConversation conversation) {
    int idx = conversations.indexWhere((m) => m.id == conversation.id);
    if (idx < 0) {
      addConversation(conversation);
    } else {
      updateConversation(conversation, idx);
    }
  }

  void updateConversationInSortedList(ServerConversation conversation) {
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(date)) {
      int idx = groupedConversations[date]!.indexWhere((element) => element.id == conversation.id);
      if (idx != -1) {
        groupedConversations[date]![idx] = conversation;
      }
    }
    notifyListeners();
  }

  (int, DateTime) addConversationWithDateGrouped(ServerConversation conversation) {
    conversations.insert(0, conversation);
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    int idx;
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var memDate = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(memDate)) {
      var convoEffectiveDate = conversation.startedAt ?? conversation.createdAt;
      idx = groupedConversations[memDate]!
          .indexWhere((element) => (element.startedAt ?? element.createdAt).isBefore(convoEffectiveDate));
      if (idx == -1) {
        groupedConversations[memDate]!.insert(0, conversation);
        idx = 0;
      } else {
        groupedConversations[memDate]!.insert(idx, conversation);
      }
    } else {
      groupedConversations[memDate] = [conversation];
      groupedConversations =
          Map.fromEntries(groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
      idx = 0;
    }
    return (idx, memDate);
  }

  void updateConversation(ServerConversation conversation, [int? index]) {
    if (index != null) {
      conversations[index] = conversation;
    } else {
      int i = conversations.indexWhere((element) => element.id == conversation.id);
      if (i != -1) {
        conversations[i] = conversation;
      }
    }
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  // _handleCalendarCreation(ServerMemory memory) {
  //   if (!SharedPreferencesUtil().calendarEnabled) return;
  //   if (SharedPreferencesUtil().calendarType != 'auto') return;
  //
  //   List<Event> events = memory.structured.events;
  //   if (events.isEmpty) return;
  //
  //   List<int> indexes = events.mapIndexed((index, e) => index).toList();
  //   setMemoryEventsState(memory.id, indexes, indexes.map((_) => true).toList());
  //   for (var i = 0; i < events.length; i++) {
  //     if (events[i].created) continue;
  //     events[i].created = true;
  //     CalendarUtil().createEvent(
  //       events[i].title,
  //       events[i].startsAt,
  //       events[i].duration,
  //       description: events[i].description,
  //     );
  //   }
  // }

  /////////////////////////////////////////////////////////////////
  ////////// Delete Memory With Undo Functionality ///////////////

  Map<String, ServerConversation> memoriesToDelete = {};
  String? lastDeletedConversationId;
  Map<String, DateTime> deleteTimestamps = {};

  void deleteConversationLocally(ServerConversation conversation, int index, DateTime date) {
    if (lastDeletedConversationId != null &&
        memoriesToDelete.containsKey(lastDeletedConversationId) &&
        DateTime.now().difference(deleteTimestamps[lastDeletedConversationId]!) < const Duration(seconds: 3)) {
      deleteConversationOnServer(lastDeletedConversationId!);
    }

    memoriesToDelete[conversation.id] = conversation;
    lastDeletedConversationId = conversation.id;
    deleteTimestamps[conversation.id] = DateTime.now();
    conversations.removeWhere((element) => element.id == conversation.id);
    groupedConversations[date]!.removeAt(index);
    if (groupedConversations[date]!.isEmpty) {
      groupedConversations.remove(date);
    }
    notifyListeners();
    Future.delayed(const Duration(seconds: 3), () {
      if (memoriesToDelete.containsKey(conversation.id) && lastDeletedConversationId == conversation.id) {
        deleteConversationOnServer(conversation.id);
      }
    });
  }

  void deleteConversationOnServer(String conversationId) {
    deleteConversationServer(conversationId);
    memoriesToDelete.remove(conversationId);
    deleteTimestamps.remove(conversationId);
    if (lastDeletedConversationId == conversationId) {
      lastDeletedConversationId = null;
    }
  }

  void undoDeletedConversation(ServerConversation conversation) {
    if (!conversations.any((e) => e.id == conversation.id)) {
      conversations.add(conversation);
      conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
      _groupConversationsByDateWithoutNotify();
    }
    memoriesToDelete.remove(conversation.id);
    deleteTimestamps.remove(conversation.id);
    if (lastDeletedConversationId == conversation.id) {
      lastDeletedConversationId = null;
    }
    notifyListeners();
  }

  /////////////////////////////////////////////////////////////////

  void deleteConversation(ServerConversation conversation, int index) {
    conversations.removeWhere((element) => element.id == conversation.id);
    deleteConversationServer(conversation.id);
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  @override
  void dispose() {
    _processingConversationWatchTimer?.cancel();
    _refreshDebounceTimer?.cancel();
    _mergeCompletedSubscription?.cancel();
    super.dispose();
  }

  void setIsFetchingConversations(bool value) {
    isFetchingConversations = value;
    notifyListeners();
  }

  // New Getter for Action Items Page
  Map<ServerConversation, List<ActionItem>> get conversationsWithActiveActionItems {
    final Map<ServerConversation, List<ActionItem>> result = {};
    final List<ServerConversation> sourceList = conversations;

    for (final convo in sourceList) {
      if (convo.discarded && !showDiscardedConversations) continue;

      final activeItems = convo.structured.actionItems.where((item) => !item.deleted).toList();
      if (activeItems.isNotEmpty) {
        result[convo] = activeItems;
      }
    }
    return result;
  }

  Future<void> updateGlobalActionItemState(
      ServerConversation conversation, String actionItemDescription, bool newState) async {
    final convoId = conversation.id;
    bool conversationFoundAndUpdated = false;

    final originalConvoIndex = conversations.indexWhere((c) => c.id == convoId);
    if (originalConvoIndex != -1) {
      final itemIndex = conversations[originalConvoIndex]
          .structured
          .actionItems
          .indexWhere((item) => item.description == actionItemDescription);
      if (itemIndex != -1) {
        conversations[originalConvoIndex].structured.actionItems[itemIndex].completed = newState;
        conversationFoundAndUpdated = true;
      }
    }

    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var dateKey = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(dateKey)) {
      final groupIndex = groupedConversations[dateKey]!.indexWhere((c) => c.id == convoId);
      if (groupIndex != -1) {
        final itemIndex = groupedConversations[dateKey]![groupIndex]
            .structured
            .actionItems
            .indexWhere((item) => item.description == actionItemDescription);
        if (itemIndex != -1) {
          groupedConversations[dateKey]![groupIndex].structured.actionItems[itemIndex].completed = newState;
        }
      }
    }

    if (conversationFoundAndUpdated) {
      // Find the item index for the server call
      final itemIndex =
          conversation.structured.actionItems.indexWhere((item) => item.description == actionItemDescription);
      if (itemIndex != -1) {
        await setConversationActionItemState(convoId, [itemIndex], [newState]);
      }
      notifyListeners();
    } else {
      debugPrint("Error: Conversation or action item not found for updateGlobalActionItemState.");
    }
  }

  void updateActionItemDescriptionInConversation(String conversationId, int itemIndex, String newDescription) {
    final convoIndex = conversations.indexWhere((c) => c.id == conversationId);
    if (convoIndex != -1) {
      if (conversations[convoIndex].structured.actionItems.length > itemIndex) {
        conversations[convoIndex].structured.actionItems[itemIndex].description = newDescription;
      }
    }

    groupedConversations.forEach((date, convoList) {
      final groupIndex = convoList.indexWhere((c) => c.id == conversationId);
      if (groupIndex != -1) {
        if (convoList[groupIndex].structured.actionItems.length > itemIndex) {
          convoList[groupIndex].structured.actionItems[itemIndex].description = newDescription;
        }
      }
    });

    notifyListeners();
  }

  Future<void> deleteActionItemAndUpdateLocally(String conversationId, int itemIndex, ActionItem actionItem) async {
    deleteConversationActionItem(conversationId, actionItem);

    final convoIndex = conversations.indexWhere((c) => c.id == conversationId);
    if (convoIndex != -1) {
      if (conversations[convoIndex].structured.actionItems.length > itemIndex) {
        conversations[convoIndex].structured.actionItems.removeAt(itemIndex);
      }
    }

    groupedConversations.forEach((date, convoList) {
      final groupConvoIndex = convoList.indexWhere((c) => c.id == conversationId);
      if (groupConvoIndex != -1) {
        if (convoList[groupConvoIndex].structured.actionItems.length > itemIndex) {
          convoList[groupConvoIndex].structured.actionItems.removeAt(itemIndex);
        }
      }
    });

    notifyListeners();
  }

  (DateTime, int) getConversationDateAndIndex(ServerConversation conversation) {
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    var idx = groupedConversations[date]!.indexWhere((element) => element.id == conversation.id);
    if (idx == -1 && groupedConversations.containsKey(date)) {
      groupedConversations[date]!.add(conversation);
    }
    return (date, idx);
  }

  int getConversationIndexById(String id, DateTime date) {
    final normalizedDate = DateTime(date.year, date.month, date.day);
    final list = groupedConversations[normalizedDate] ?? [];
    return list.indexWhere((c) => c.id == id);
  }

  void updateSyncedConversation(ServerConversation conversation) {
    updateConversationInSortedList(conversation);
    notifyListeners();
  }

  // ***************************************
  // ******** MERGE FUNCTIONALITY **********
  // ***************************************

  /// Check if a conversation is currently being merged
  /// Checks both local state and the conversation's actual status from server
  bool isConversationMerging(String conversationId) {
    // Check local tracking
    if (mergingConversationIds.contains(conversationId)) {
      return true;
    }
    // Check actual conversation status from server
    final convo = conversations.firstWhere(
      (c) => c.id == conversationId,
      orElse: () => conversations.isNotEmpty ? conversations.first : conversations.first,
    );
    if (convo.id == conversationId && convo.status == ConversationStatus.merging) {
      return true;
    }
    return false;
  }

  /// Enter selection mode for merge
  void enterSelectionMode() {
    isSelectionModeActive = true;
    selectedConversationIds.clear();
    MixpanelManager().conversationMergeSelectionModeEntered();
    notifyListeners();
  }

  /// Exit selection mode and clear selections
  void exitSelectionMode() {
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    MixpanelManager().conversationMergeSelectionModeExited();
    notifyListeners();
  }

  List<String> markSelectedAsMergingAndExit() {
    final idsToMerge = selectedConversationIds.toList();
    mergingConversationIds.addAll(idsToMerge);
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    notifyListeners();
    return idsToMerge;
  }

  /// Toggle selection of a conversation
  void toggleConversationSelection(String conversationId) {
    if (isConversationMerging(conversationId)) {
      // Don't allow selection of conversations being merged
      return;
    }
    if (selectedConversationIds.contains(conversationId)) {
      selectedConversationIds.remove(conversationId);
      // Auto-exit selection mode if no items remain selected
      if (selectedConversationIds.isEmpty) {
        isSelectionModeActive = false;
      }
    } else {
      selectedConversationIds.add(conversationId);
      MixpanelManager().conversationSelectedForMerge(conversationId, selectedConversationIds.length);
    }
    notifyListeners();
  }

  /// Check if a conversation is selected
  bool isConversationSelected(String conversationId) {
    return selectedConversationIds.contains(conversationId);
  }

  /// Get selected conversations sorted by creation date (earliest first)
  List<ServerConversation> get selectedConversations {
    final selected = conversations.where((c) => selectedConversationIds.contains(c.id)).toList();
    selected.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    return selected;
  }

  /// Check if a conversation is eligible for merge selection
  ///
  /// A conversation is eligible if:
  /// - It's not locked
  /// - It's not currently being merged
  ///
  /// No time gap restrictions - user can merge any conversations they want.
  bool isConversationEligibleForMerge(String conversationId) {
    // Find the conversation
    final convo = conversations.firstWhere(
      (c) => c.id == conversationId,
      orElse: () => conversations.first,
    );
    if (convo.id != conversationId) return false;

    if (convo.isLocked) {
      return false;
    }

    if (mergingConversationIds.contains(conversationId)) {
      return false;
    }

    return true;
  }

  /// Check if merge is allowed (at least 2 conversations selected)
  bool get canMerge => selectedConversationIds.length >= 2;

  /// Initiate merge of selected conversations
  Future<MergeConversationsResponse?> initiateConversationMerge({List<String>? conversationIds}) async {
    final idsToMerge = conversationIds ?? selectedConversationIds.toList();
    if (idsToMerge.length < 2) return null;

    // Call merge API
    final response = await mergeConversations(idsToMerge);
    MixpanelManager().conversationMergeInitiated(idsToMerge);

    if (response == null) {
      MixpanelManager().conversationMergeFailed(idsToMerge);
      if (conversationIds != null) {
        for (final id in conversationIds) {
          mergingConversationIds.remove(id);
        }
        notifyListeners();
      }
    } else if (conversationIds == null) {
      mergingConversationIds.addAll(idsToMerge);
      exitSelectionMode();
      notifyListeners();
    }

    return response;
  }

  /// Handle merge completion from FCM notification
  Future<void> onMergeCompleted(String mergedConversationId, List<String> removedConversationIds) async {
    // Remove merging status for ALL involved conversations
    mergingConversationIds.remove(mergedConversationId);
    for (final id in removedConversationIds) {
      mergingConversationIds.remove(id);
    }

    MixpanelManager().conversationMergeCompleted(mergedConversationId, removedConversationIds);

    // Remove deleted conversations from local state
    for (final id in removedConversationIds) {
      conversations.removeWhere((c) => c.id == id);
    }

    // Fetch updated merged conversation
    final mergedConvo = await getConversationById(mergedConversationId);
    if (mergedConvo != null) {
      final idx = conversations.indexWhere((c) => c.id == mergedConversationId);
      if (idx != -1) {
        conversations[idx] = mergedConvo;
      } else {
        conversations.insert(0, mergedConvo);
      }
      conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    }

    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }
}
