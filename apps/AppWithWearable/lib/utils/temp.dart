List<Message> retrieveMostRecentMessages(List<Message> ogChatHistory, {int count = 5}) {
  if (ogChatHistory.length > count) {
    return ogChatHistory.sublist(ogChatHistory.length - count);
  }
  return ogChatHistory;
}


void _setTimeagoLocales() {
  timeago.setLocaleMessages('en', timeago.EnMessages());
  timeago.setLocaleMessages('en_short', timeago.EnShortMessages());
}

String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) {
    return '';
  }
  if (format == 'relative') {
    _setTimeagoLocales();
    return timeago.format(dateTime, locale: locale, allowFromNow: true);
  }
  return DateFormat(format, locale).format(dateTime);
}
