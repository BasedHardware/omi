import 'package:sentry_flutter/sentry_flutter.dart';

addDeepgramEventContext(String event) {
  // TODO: instead of doing this, include a way to add single events that can be traced and combined
  // click x, bluetooth disconnected, ws disconnected, click, ws connected ... etc..
  Sentry.configureScope((scope) {
    var deepgramData = (scope.contexts['deepgram'] ?? {});
    var currentEvents = deepgramData['events'] ?? [];
    currentEvents.add(event);
    deepgramData['events'] = currentEvents;
    scope.setContexts('deepgram', deepgramData);
  });
}
