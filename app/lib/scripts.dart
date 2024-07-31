import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/preferences.dart';

scriptMemoryVectorsExecuted() async {
  // FUCK, there was a very stupid issue.
  // vectors were overwritten for each user, as the id of the vector was the memory id of the local db (0,1,2...)
  // This aims to fix that
  if (SharedPreferencesUtil().scriptMemoryVectorsExecuted) return;
  debugPrint('scriptMemoryVectorsExecuted');
  var memories = MemoryProvider().getMemoriesOrdered();
  if (memories.isEmpty) {
    SharedPreferencesUtil().scriptMemoryVectorsExecuted = true;
    return;
  }
  for (var i = 0; i < memories.length; i++) {
    var f = getEmbeddingsFromInput(memories[i].structured.toString()).then((vector) {
      debugPrint('Memory: ${i + 1}');
      upsertPineconeVector(memories[i].id.toString(), vector, memories[i].createdAt);
    });
    if (i % 10 == 0) {
      await f;
      await Future.delayed(const Duration(seconds: 1));
      debugPrint('Processing Memory: $i');
    }
  }

  debugPrint('migrateMemoriesCategoriesAndEmojis completed');
  SharedPreferencesUtil().scriptMemoryVectorsExecuted = true;
}

// CONSIDER rerunning the summary prompt on memories, so the vector is better.

// Next steps for summarization of memories.

// var f = getSemanticSummariesForEmbedding(memories[i].transcript).then((summaries) async {
//   debugPrint('Memory: ${i + 1}');
//   for (var summary in summaries) {
//     List<double> vector = await getEmbeddingsFromInput(summary);
//     await upsertPineconeVector(memories[i].id.toString(), vector, memories[i].createdAt);
//     debugPrint('summary: $summary');
//   }
// });
