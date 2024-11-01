import 'package:friend_private/utils/logger.dart';
import 'package:mockito/mockito.dart';

class MockLogger extends Mock implements LoggerService {
  static final MockLogger _instance = MockLogger._internal();
  factory MockLogger() => _instance;
  MockLogger._internal();
}
