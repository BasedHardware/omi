import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/preferences.dart';

scriptMigrateMemoriesToBack() async {
  if (SharedPreferencesUtil().scriptMigrateMemoriesToBack) return;
  var memoriesJson = MemoryProvider().getMemories().map((e) => e.toJson()).toList();
  await migrateMemoriesToBackend(memoriesJson);
  SharedPreferencesUtil().scriptMigrateMemoriesToBack = true;
}