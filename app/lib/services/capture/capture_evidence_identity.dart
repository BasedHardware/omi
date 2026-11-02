import 'package:uuid/uuid.dart';

/// Keeps source-frame evidence scoped to one WAL lifetime and account.
class CaptureEvidenceIdentity {
  Object? _source;
  int? _generation;
  String? _uid;
  String? _root;

  String rootFor(Object source, int generation, String? uid) {
    if (!identical(source, _source) || generation != _generation || uid != _uid) {
      _root = null;
      _source = source;
      _generation = generation;
      _uid = uid;
    }
    return _root ??= const Uuid().v4();
  }

  void reset() => _root = null;
}
