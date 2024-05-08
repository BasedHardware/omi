enum VectorDBError {
  collectionAlreadyExists,
}

class CollectionError implements Exception {
  CollectionError._(this.message);

  final String message;

  factory CollectionError.fileNotFound() {
    return CollectionError._("File not found.");
  }

  factory CollectionError.loadFailed(String errorMessage) {
    return CollectionError._("Load failed: $errorMessage");
  }

  @override
  String toString() {
    return message;
  }
}