// Compact Home page and preparation transport with typed failure handling.
// Card decoding stays separate from hydrated conversation and episode detail.
import 'dart:convert';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/backend/schema/gen/home_feed_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/off_ui_isolate.dart';

class HomeFeedApi {
  HomeFeedApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? 'http://127.0.0.1:8000/';
  final String baseUrl;
  final ApiSend? send;
  Future<ApiResult<HomeFeedPage>> page({String? cursor}) async {
    // Typed transport owns auth, replay and error taxonomy. Decode the bounded raw envelope off-isolate.
    final result = await executeApi<String>(
        request: ApiRequest(
            method: 'GET',
            url: Uri.parse('${baseUrl}v1/home/feed')
                .replace(queryParameters: {'limit': '50', if (cursor != null) 'cursor': cursor}).toString()),
        send: send,
        decode: (body) => body);
    if (result is ApiFailure<String>) return ApiFailure(result.problem);
    final body = (result as ApiSuccess<String>).data;
    try {
      final page = await offUiIsolate(() => HomeFeedPage.fromJson(jsonDecode(body) as Map<String, dynamic>),
          size: body.length, threshold: 16 * 1024, debugName: 'home-feed-decode');
      return ApiSuccess(page);
    } on FormatException {
      return const ApiFailure(ApiProblem(ApiProblemKind.decode));
    } on TypeError {
      return const ApiFailure(ApiProblem(ApiProblemKind.decode));
    }
  }
}

class HomeFeedPreparation {
  const HomeFeedPreparation({required this.ready, required this.processed, required this.hasMore});
  final bool ready, hasMore;
  final int processed;
}

extension HomeFeedPreparationApi on HomeFeedApi {
  Future<ApiResult<HomeFeedPreparation>> prepare() => executeApi(
      request: ApiRequest(method: 'POST', url: '${baseUrl}v1/home/feed/prepare'),
      send: send,
      decode: (body) {
        final j = jsonDecode(body);
        if (j is! Map || j['ready'] is! bool || j['processed'] is! int || j['has_more'] is! bool) {
          throw const FormatException('Invalid preparation response');
        }
        final value = wire.GeneratedHomeFeedPreparationResponse.fromJson(Map<String, dynamic>.from(j));
        return HomeFeedPreparation(ready: value.ready, processed: value.processed, hasMore: value.hasMore);
      });
}
