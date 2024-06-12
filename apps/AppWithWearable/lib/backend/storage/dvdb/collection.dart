import 'dart:convert';
import 'dart:core';
import 'dart:io';
import 'dart:typed_data';

import 'package:friend_private/backend/storage/dvdb/document.dart';
import 'package:friend_private/backend/storage/dvdb/math.dart';
import 'package:friend_private/backend/storage/dvdb/search_result.dart';
import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

class Collection {
  Collection(this.name);

  final String name;
  final Map<String, Document> documents = {};

  void addDocument(String? id, String text, Float64List embedding, {Map<String, String>? metadata}) {
    var uuid = const Uuid();
    final Document document = Document(
      id: id ?? uuid.v1(),
      text: text,
      embedding: embedding,
      metadata: metadata,
    );

    documents[document.id] = document;
    _writeDocument(document);
  }

  void addDocuments(List<Document> docs) {
    for (final Document doc in docs) {
      documents[doc.id] = doc;
      _writeDocument(doc);
    }
  }

  void removeDocument(String id) {
    if (documents.containsKey(id)) {
      documents.remove(id);
      _saveAllDocuments(); // Re-saving all documents after removal
    }
  }

  List<SearchResult> search(Float64List query, {int numResults = 10, double? threshold}) {
    final List<SearchResult> similarities = <SearchResult>[];
    for (var document in documents.values) {
      final double similarity = MathFunctions().cosineSimilarity(query, document.embedding);

      if (threshold != null && similarity < threshold) {
        continue;
      }

      similarities.add(SearchResult(id: document.id, text: document.text, score: similarity));
    }

    similarities.sort((SearchResult a, SearchResult b) => b.score.compareTo(a.score));
    return similarities.take(numResults).toList();
  }

  Future<void> _writeDocument(Document document) async {
    Directory documentsDirectory = await getApplicationDocumentsDirectory();
    String path = join(documentsDirectory.path, '$name.json');
    final File file = File(path);

    var encodedDocument = json.encode(document.toJson());
    List<int> bytes = utf8.encode('$encodedDocument\n');

    file.writeAsBytesSync(bytes, mode: FileMode.append);
  }

  Future<void> _saveAllDocuments() async {
    Directory documentsDirectory = await getApplicationDocumentsDirectory();
    String path = join(documentsDirectory.path, '$name.json');
    final File file = File(path);

    file.writeAsStringSync(''); // Clearing the file
    for (var document in documents.values) {
      _writeDocument(document);
    }
  }

  Future<void> load() async {
    Directory documentsDirectory = await getApplicationDocumentsDirectory();
    String path = join(documentsDirectory.path, '$name.json');
    final File file = File(path);

    if (!file.existsSync()) {
      documents.clear();
      return;
    }

    final lines = file.readAsLinesSync();

    for (var line in lines) {
      var decodedDocument = json.decode(line) as Map<String, dynamic>;
      var document = Document.fromJson(decodedDocument);
      documents[document.id] = document;
    }
  }

  void clear() {
    documents.clear();
    _saveAllDocuments();
  }
}
