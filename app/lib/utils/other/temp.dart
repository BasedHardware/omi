import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:omi/utils/l10n_extensions.dart';

String dateTimeFormat(String format, DateTime? dateTime, {String? locale}) {
  if (dateTime == null) return '';
  return DateFormat(format, locale).format(dateTime);
}

Future routeToPage(BuildContext context, Widget page, {bool replace = false}) {
  if (!context.mounted) {
    return Future.value();
  }

  var route = Platform.isIOS ? CupertinoPageRoute(builder: (c) => page) : MaterialPageRoute(builder: (c) => page);
  if (replace) {
    return Navigator.of(context).pushAndRemoveUntil(route, (route) => false);
  }
  return Navigator.of(context).push(route);
}

String formatChatTimestamp(DateTime dateTime, {BuildContext? context}) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);
  final timeStr = dateTimeFormat('h:mm a', dateTime);

  if (messageDate == today) {
    // Today, show time only
    return timeStr;
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    if (context != null) {
      return context.l10n.yesterdayAtTime(timeStr);
    }
    return 'Yesterday $timeStr';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}

String countryFlagFromCode(String countryCode) {
  const flagOffset = 0x1F1E6;
  const asciiOffset = 0x41;

  final firstChar = countryCode.codeUnitAt(0) - asciiOffset + flagOffset;
  final secondChar = countryCode.codeUnitAt(1) - asciiOffset + flagOffset;

  return String.fromCharCode(firstChar) + String.fromCharCode(secondChar);
}
