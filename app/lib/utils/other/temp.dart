import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) return '';
  return DateFormat(format, locale).format(dateTime);
}

Future routeToPage(BuildContext context, Widget page, {bool replace = false}) {
  var route = Platform.isIOS ? CupertinoPageRoute(builder: (c) => page) : MaterialPageRoute(builder: (c) => page);
  if (replace) {
    if (context.mounted) {
      return Navigator.of(context).pushAndRemoveUntil(route, (route) => false);
    }
  }
  return Navigator.of(context).push(route);
}

String formatChatTimestamp(DateTime dateTime) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);

  if (messageDate == today) {
    // Today, show time only
    return dateTimeFormat('h:mm a', dateTime);
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    return 'Yesterday ${dateTimeFormat('h:mm a', dateTime)}';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
