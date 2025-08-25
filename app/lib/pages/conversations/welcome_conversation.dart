import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

ServerConversation buildWelcomeConversation() {
  final now = DateTime.now();

  final structured = Structured(
    'Welcome to Omi',
    "Omi captures moments, meetings or thoughts and turns them into clear summaries with action items.\n"
        "1) Start recording 🎙️: Tap the big Record button to begin recording, and Omi will capture your conversation or thoughts.\n"
        "2) Stop or auto-finish ⏹️: Tap the red stop button to stop. If you're silent for ~2 minutes, Omi auto-finishes and summarizes.\n"
        "3) Review your summary 📝: The new conversation appears at the top with a title, overview, and TODOs.\n"
        "4) Share when needed 🔗: Open a conversation, tap Share, then Send web URL.\n"
        "5) Automate workflows ⚙️: Connect apps to trigger actions when conversations finish - like creating reminders, or updating other tools.",
    emoji: '👋',
    category: 'education',
  );

  structured.actionItems = [
    ActionItem('Try a quick 1-2 minute test recording from the Home screen'),
    ActionItem('Open the new conversation and read the summary'),
    ActionItem('Share the URL with someone'),
  ];

  return ServerConversation(
    id: 'welcome',
    createdAt: now,
    startedAt: now,
    finishedAt: now,
    structured: structured,
    source: ConversationSource.omi,
    language: 'en',
    status: ConversationStatus.completed,
  );
}
