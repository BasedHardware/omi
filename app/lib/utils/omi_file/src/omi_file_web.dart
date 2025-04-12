import 'dart:convert';
import 'package:idb_shim/idb_browser.dart';
import 'package:omi/utils/omi_file/omi_file_interface.dart';

class OmiFile implements IOmiFile {
  static const _dbName = 'omi_file_db';
  static const _storeName = 'omi_files';

  final String _path;
  Database? _db;

  OmiFile(this._path);

  Future<Database> get _database async {
    if (_db != null) return _db!;
    final factory = idbFactoryBrowser;
    _db = await factory.open(_dbName, version: 1, onUpgradeNeeded: (e) {
      e.database.createObjectStore(_storeName);
    });
    return _db!;
  }

 

  @override
  Future<OmiFile> create() async {
    await writeAsString('');
    return this;
  }

  @override
  void createSync() => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<OmiFile> delete() async {
    final db = await _database;
    await db.transaction(_storeName, idbModeReadWrite).objectStore(_storeName).delete(_path);
    return this;
  }

  @override
  void deleteSync() => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<bool> exists() async {
    final db = await _database;
    final value = await db.transaction(_storeName, idbModeReadOnly).objectStore(_storeName).getObject(_path);
    return value != null;
  }

  @override
  Future<DateTime> lastModified() async {
    throw UnsupportedError('lastModified not supported on web');
  }

  @override
  DateTime lastModifiedSync() => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  String get name => _path.split('/').last;

  @override
  String get path => _path;

  @override
  Future<List<int>> readAsBytes() async {
    final str = await readAsString();
    return utf8.encode(str);
  }

  @override
  List<int> readAsBytesSync() => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<String> readAsString() async {
    final db = await _database;
    final data = await db.transaction(_storeName, idbModeReadOnly).objectStore(_storeName).getObject(_path);
    return data?.toString() ?? '';
  }

  @override
  String readAsStringSync() => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<OmiFile> rename(String newName) async {
    final contents = await readAsString();
    await delete();
    final newFile = OmiFile(newName);
    await newFile.writeAsString(contents);
    return newFile;
  }

  @override
  void renameSync(String newName) => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  int get size => throw UnsupportedError('Use sizeAsync on web');

  Future<int> get sizeAsync async {
    final bytes = await readAsBytes();
    return bytes.length;
  }

  @override
  Future<OmiFile> writeAsBytes(List<int> bytes) async {
    await writeAsString(utf8.decode(bytes));
    return this;
  }

  @override
  void writeAsBytesSync(List<int> bytes) => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<OmiFile> writeAsString(String contents) async {
    final db = await _database;
    await db.transaction(_storeName, idbModeReadWrite).objectStore(_storeName).put(contents, _path);
    return this;
  }

  @override
  void writeAsStringSync(String contents) => throw UnsupportedError('Sync operations are not supported on the web');

  @override
  Future<OmiFile> append(String contents) async {
    final existing = await readAsString();
    await writeAsString(existing + contents);
    return this;
  }

  @override
  void appendSync(String contents) => throw UnsupportedError('Sync operations are not supported on the web');

}
