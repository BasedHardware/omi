/// Development and debugging configuration constants
///
/// This file contains flags and settings used during development and testing.
/// These should not contain sensitive information or API keys.
class DevConstants {

  /// For useMockData
  /// Toggle to use mock data instead of real API calls
  ///
  /// WHAT WORKS WITH MOCK DATA (useMockData = true):
  /// ✅ Conversations list - displays 5 hardcoded conversations
  /// ✅ Memories tab - displays 15 hardcoded memories
  /// ✅ Stats widget - shows correct counts (conversations, memories, words)
  /// ✅ UI/UX testing - test app flows without microphone or backend access
  /// ✅ Simulator/emulator testing - no need for physical device or API
  ///
  /// WHAT DOESN'T WORK WITH MOCK DATA (known limitations):
  /// ❌ AI Chat memory context - Chat will NOT have access to mock memories
  ///    Reason: Chat sends messages to the real backend API (/v2/messages),
  ///    and the backend queries its own database for memories to provide AI context.
  ///    Mock memories only exist in the app's UI layer, not in the backend database.
  ///    The AI will respond, but without any personal memory context.
  /// ❌ Real-time features - Notifications, syncing, etc. still require backend
  /// ❌ Plugin/App integrations - External integrations require real API calls
  ///
  /// WHEN TO USE EACH MODE:
  /// - Set to TRUE: Testing UI, layouts, navigation, stats without backend/microphone
  /// - Set to FALSE: Testing full app functionality, AI chat with memory context, production
  ///
  /// IMPLEMENTATION DETAILS:
  /// - ConversationProvider._loadMockConversations() - 5 conversations with ~120 words
  /// - MemoriesProvider._generateMockMemories() - 15 memories across categories
  /// - Both providers check this flag to skip API calls when enabled
  ///
  /// Set this to true for simulator/emulator testing, false for production or full testing
  static const bool useMockData = true;

  // Prevent instantiation - this is a constants-only class
  DevConstants._();
}
