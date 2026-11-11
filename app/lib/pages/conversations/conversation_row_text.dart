import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' show ConversationUntitledRenderedSurface;
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// The row title for a conversation (hub audit #21): its title, else its transcript text (legacy
/// rows the server left untitled), a recording date/time when neither exists, and
/// "Discarded · 12s" for a discarded one (its words go in [conversationSnippet]).
String conversationRowTitle(BuildContext context, ServerConversation conversation) {
  final l10n = context.l10n;
  // A noise clip revealed from Home's fold reads like any row, not as "Discarded".
  if (conversation.discarded && !conversation.isFoldedNoise) {
    final seconds = conversation.getDurationInSeconds();
    if (seconds <= 0) return l10n.discardedConversation;
    return l10n.discardedConversationTitle(OmiDuration.compact(seconds, l10n));
  }
  return conversationDisplayTitle(
    conversation,
    l10n,
    surface: ConversationUntitledRenderedSurface.list,
    dates: OmiDateFormat.of(context),
    title: conversation.structured.title.decodeString,
  );
}

/// A plain-text preview of what was said: the transcript words without timestamps or speaker
/// prefixes, newest last, trimmed to [maxChars] at a word boundary.
String conversationSnippet(ServerConversation conversation, {int maxChars = 160}) {
  // Only collect the visible prefix plus one character to decide whether it
  // needs an ellipsis. Hydrated/retained conversations can have hours of text;
  // joining all of it for each scrolling row makes a short preview O(history).
  final prefix = StringBuffer();
  for (final segment in conversation.transcriptSegments) {
    final words = segment.text.trim();
    if (words.isEmpty) continue;
    if (prefix.isNotEmpty) prefix.write(' ');
    final remaining = maxChars + 1 - prefix.length;
    if (remaining > 0) prefix.write(words.length > remaining ? words.substring(0, remaining) : words);
    if (prefix.length > maxChars) break;
  }
  final text = prefix.toString();
  if (text.length <= maxChars) return text;
  final cut = text.substring(0, maxChars);
  final space = cut.lastIndexOf(' ');
  return '${space > maxChars ~/ 2 ? cut.substring(0, space) : cut}…';
}
