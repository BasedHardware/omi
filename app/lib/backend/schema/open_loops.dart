/// Wire models for the open-loop cards in Review ("Questions for you").
///
/// A card is self-contained by contract: the question and context line the card
/// writer rendered are shown verbatim. Parsing goes through the generated
/// review wire models: a row that fails the wire contract, or loses an identity
/// field (id, date, question), is dropped — never shown half-built. An empty
/// context line stays empty and the card simply renders without one.
library;

import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;

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

  static OpenLoopCard? fromGenerated(wire.GeneratedOpenLoopCard generated) {
    if (generated.cardId.isEmpty || generated.date.isEmpty || generated.question.isEmpty) return null;
    return OpenLoopCard(
      cardId: generated.cardId,
      date: generated.date,
      question: generated.question,
      contextLine: generated.contextLine,
    );
  }
}

class OpenLoopCardsResponse {
  const OpenLoopCardsResponse({required this.cards});
  final List<OpenLoopCard> cards;

  /// The listing tolerates a card the writer never should have produced: every
  /// row is decoded through the generated contract first, and rows that fail it
  /// (or lose an identity field) are dropped, so one bad card cannot fail the
  /// whole day's listing.
  static OpenLoopCardsResponse fromGeneratedWireJson(Map<String, dynamic> json) {
    final cards = <OpenLoopCard>[];
    final rawCards = json['cards'];
    if (rawCards is List) {
      for (final row in rawCards.whereType<Map<String, dynamic>>()) {
        try {
          final card = OpenLoopCard.fromGenerated(wire.GeneratedOpenLoopCard.fromJson(row));
          if (card != null) cards.add(card);
        } on FormatException {
          continue;
        }
      }
    }
    return OpenLoopCardsResponse(cards: cards);
  }
}

class OpenLoopAnswerResult {
  const OpenLoopAnswerResult({required this.cardId, required this.state});
  final String cardId;
  final String state;

  static OpenLoopAnswerResult fromGenerated(wire.GeneratedOpenLoopAnswerResponse generated) =>
      OpenLoopAnswerResult(cardId: generated.cardId, state: generated.state);
}
