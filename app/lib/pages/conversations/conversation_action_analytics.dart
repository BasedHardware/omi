import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

export 'package:omi/utils/analytics/registry/events.g.dart' show ConversationActionAction, ConversationActionSurface;

/// Records one tap on a conversation action (David, 2026-09-24: learn which actions earn their
/// place). Only the action and the surface it came from — never ids, titles or content.
void trackConversationAction(ConversationActionAction action, ConversationActionSurface surface) =>
    const TypedEvents().emit(ConversationAction(action: action, surface: surface));
