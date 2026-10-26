import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/env/env.dart';

/// The open-loop cards in Review ("Questions for you"). Every call returns a
/// typed [ApiResult]. An empty list means the day's cards are gone or the
/// feature is off — the Review page then looks exactly as it does without it.
///
/// A 409 from the answer call means the card was already answered elsewhere
/// (for example on another device); it stays answered.

String _id(String id) => Uri.encodeComponent(id);

Future<ApiResult<OpenLoopCardsResponse>> getOpenLoopCards() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/review/open-loops', method: 'GET'),
      decode: (body) => OpenLoopCardsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>),
    );

Future<ApiResult<OpenLoopAnswerResult>> answerOpenLoopCard(OpenLoopCard card, OpenLoopAction action) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/review/open-loops/${_id(card.date)}/${_id(card.cardId)}/answer',
        method: 'POST',
        body: jsonEncode({'action': action.wire}),
      ),
      decode: (body) =>
          OpenLoopAnswerResult.fromJson(jsonDecode(body) as Map<String, dynamic>) ??
          (throw const FormatException('Malformed OpenLoopAnswerResult')),
    );
