import 'package:talker_flutter/talker_flutter.dart';

class Logger {
  static final Logger instance = Logger._internal();
  final Talker talker = Talker();

  Logger._internal();

  void error(String message, [dynamic error, StackTrace? stackTrace]) {
    print('❌ ERROR: $message');
    if (error != null) print(error);
    if (stackTrace != null) print(stackTrace);
    talker.error(message, error, stackTrace);
  }

  void warn(String message) {
    print('⚠️ WARNING: $message');
    talker.warning(message);
  }

  static void handle(Exception error, StackTrace stackTrace, {String? message}) {
    instance.error(message ?? error.toString(), error, stackTrace);
  }

  static void log(String message) {
    print('📝 LOG: $message');
    instance.talker.debug(message);
  }
}
