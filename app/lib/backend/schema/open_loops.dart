/// Wire models for the open-loop cards in Review ("Questions for you").
///
/// A card is self-contained by contract: the question and context line the card
/// writer rendered are shown verbatim. Parsing mirrors the review wire models —
/// strict about identity fields (a card without an id, date or question is
/// dropped), lenient about the optional context line.
library;

String? _str(Object? v) => v is String && v.isNotEmpty ? v : null;

/// The three answers a card accepts; mirrors the backend `CARD_ACTIONS`.
enum OpenLoopAction { done, remind, drop }

extension OpenLoopActionWire on OpenLoopAction {
  String get wire => switch (this) {
        OpenLoopAction.done => 'done',
        OpenLoopAction.remind => 'remind',
        OpenLoopAction.drop => 'drop',
      };
}

class OpenLoopCard {
  const OpenLoopCard({
    required this.cardId,
    required this.date,
    required this.question,
    this.contextLine = '',
  });

  final String cardId;

  /// The recap day the card belongs to; part of the answer endpoint's path.
  final String date;
  final String question;
  final String contextLine;

  static OpenLoopCard? fromJson(Map<String, dynamic> json) {
    final id = _str(json['card_id']);
    final date = _str(json['date']);
    final question = _str(json['question']);
    if (id == null || date == null || question == null) return null;
    return OpenLoopCard(cardId: id, date: date, question: question, contextLine: _str(json['context_line']) ?? '');
  }

  static List<OpenLoopCard> listFrom(Object? v) => v is List
      ? v.whereType<Map<String, dynamic>>().map(fromJson).whereType<OpenLoopCard>().toList(growable: false)
      : const [];
}

class OpenLoopCardsResponse {
  const OpenLoopCardsResponse({required this.cards});
  final List<OpenLoopCard> cards;

  static OpenLoopCardsResponse fromJson(Map<String, dynamic> json) =>
      OpenLoopCardsResponse(cards: OpenLoopCard.listFrom(json['cards']));
}

class OpenLoopAnswerResult {
  const OpenLoopAnswerResult({required this.cardId, required this.state});
  final String cardId;
  final String state;

  static OpenLoopAnswerResult? fromJson(Map<String, dynamic> json) {
    final id = _str(json['card_id']);
    final state = _str(json['state']);
    if (id == null || state == null) return null;
    return OpenLoopAnswerResult(cardId: id, state: state);
  }
}
