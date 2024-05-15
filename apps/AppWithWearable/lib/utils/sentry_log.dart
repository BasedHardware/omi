import 'package:flutter/material.dart';
import 'package:logging/logging.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

final log = Logger('SentryLogger');

addEventToContext(String event) {
  // TODO: instead of doing this, include a way to add single events that can be traced and combined
  // click x, bluetooth disconnected, ws disconnected, click, ws connected ... etc..
  debugPrint(event);
  log.info(event);
  // Sentry.configureScope((scope) {
  //   var deepgramData = (scope.contexts['events'] ?? {});
  //   var currentEvents = deepgramData['values'] ?? [];
  //   currentEvents.add(event);
  //   deepgramData['values'] = currentEvents;
  //   scope.setContexts('events', deepgramData);
  // });
}
