import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:intl/intl.dart';

List<Message> retrieveMostRecentMessages(List<Message> ogChatHistory, {int count = 5}) {
  if (ogChatHistory.length > count) return ogChatHistory.sublist(ogChatHistory.length - count);
  return ogChatHistory;
}

String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) return '';
  return DateFormat(format, locale).format(dateTime);
}

Future routeToPage(BuildContext context, Widget page, {bool replace = false}) {
  var route = Platform.isIOS ? CupertinoPageRoute(builder: (c) => page) : MaterialPageRoute(builder: (c) => page);
  if (replace) {
    return Navigator.of(context).pushReplacement(route);
  }
  return Navigator.of(context).push(route);
}
