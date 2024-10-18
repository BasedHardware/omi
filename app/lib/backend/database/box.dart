import 'package:objectbox/objectbox.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import '../../objectbox.g.dart';

class ObjectBox {
  /// The Store of this app.
  late final Store store;

  ObjectBox._create(this.store) {
    // Add any additional setup code, e.g. build queries.
  }

  /// Create an instance of ObjectBox to use throughout the app.
  static Future<ObjectBox> create() async {
    final docsDir = await getApplicationDocumentsDirectory();
    // Future<Store> openStore() {...} is defined in the generated objectbox.g.dart
    final store = await openStore(directory: p.join(docsDir.path, "obx-example"));
    return ObjectBox._create(store);
  }
}

class ObjectBoxUtil {
  static final ObjectBoxUtil _instance = ObjectBoxUtil._internal();
  static ObjectBox? _box;

  factory ObjectBoxUtil() {
    return _instance;
  }

  ObjectBoxUtil._internal();

  static Future<void> init() async {
    _box = await ObjectBox.create();
  }

  ObjectBox? get box => _box;
}
