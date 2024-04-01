import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:timeago/timeago.dart' as timeago;
import 'lat_lng.dart';
import 'place.dart';
import 'uploaded_file.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';

DateTime? sinceLastMonth() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 730));
  return twentyFourHoursAgo;
}

DateTime? sinceYesterday() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 24));
  return twentyFourHoursAgo;
}

DateTime? sinceLastWeek() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 168));
  return twentyFourHoursAgo;
}

DateTime? since18hoursago() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime eighteenHoursAgo = now.subtract(Duration(hours: 24));
  return eighteenHoursAgo;
}
