import 'package:friend_private/backend/storage/message.dart';
import 'package:intl/intl.dart';

List<Message> retrieveMostRecentMessages(List<Message> ogChatHistory, {int count = 5}) {
  if (ogChatHistory.length > count) {
    return ogChatHistory.sublist(ogChatHistory.length - count);
  }
  return ogChatHistory;
}

String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) return '';
  return DateFormat(format, locale).format(dateTime);
}
