import 'dart:typed_data';

import 'package:friend_private/backend/storage/dvdb/dvdb_helper.dart';
import 'package:friend_private/backend/storage/memories.dart';

var collection = DVDB().collection("memories");

// Future<void> storeMemoryVector(MemoryRecord memory, List<double> embedding) async {
//   collection.addDocument(memory.id, memory.getStructuredString(), Float64List.fromList(embedding));
// }

List<String> querySimilarVectors(List<double> queryEmbedding) {
  final query = collection.search(Float64List.fromList(queryEmbedding), numResults: 10);
  return query.map((e) => e.id).toList();
}
