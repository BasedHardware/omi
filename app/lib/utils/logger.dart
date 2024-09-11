import 'package:talker_flutter/talker_flutter.dart';

class Logger {
  final talker = TalkerFlutter.init();

  Logger._();

  static final Logger _instance = Logger._();

  static Logger get instance => _instance;

  static void log(dynamic message) {
    instance.talker.log(message);
  }

  static void error(dynamic message) {
    instance.talker.error(message);
  }

  static void warning(dynamic message) {
    instance.talker.warning(message);
  }

  static void info(dynamic message) {
    instance.talker.info(message);
  }

  static void debug(dynamic message) {
    instance.talker.debug(message);
  }

  static void handle(dynamic exception, StackTrace? stackTrace, {String? message}) {
    instance.talker.handle(exception, stackTrace, message ?? 'An error occurred. Please try again later.');
  }
}
