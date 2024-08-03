import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';

scriptMigrateMemoriesToBack() async {
  // if (SharedPreferencesUtil().scriptMigrateMemoriesToBack) return;
  var memoriesJson = MemoryProvider().getMemories().map((e) => e.toJson()).toList();
  if (memoriesJson.isNotEmpty) await migrateMemoriesToBackend(memoriesJson);
  SharedPreferencesUtil().scriptMigrateMemoriesToBack = true;
}
