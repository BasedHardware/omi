// Reliability experiment `early_title_icon`: an ended conversation shows its title and emoji on Home
// as soon as the server has fixed them, instead of a "Processing…" row until its summary is stored.

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/utils/reliability_experiments.dart';

const earlyTitleIconExperiment = 'early_title_icon';

/// Whether the server has ended this conversation and fixed its title and emoji while its transcript
/// is still arriving or its summary is still being written. The server sets both when it commits the
/// ended conversation with its outline (`title_locked`), seconds before the summary is stored, and
/// the summary step keeps them. A recording document, an untitled row and a row whose title can still
/// change never qualify. Off, always false.
bool titledBeforeSummary(ServerConversation conversation) {
  final v3 = conversation.v3;
  if (v3 == null || v3.recording || !v3.titleLocked) return false;
  if (v3.tileState != ConversationTileState.transcribing && v3.tileState != ConversationTileState.writing) {
    return false;
  }
  if (conversation.structured.title.trim().isEmpty || conversation.structured.emoji.trim().isEmpty) return false;
  return ReliabilityExperiments.enabled(earlyTitleIconExperiment);
}
