import 'dart:io';

import 'package:omi/utils/omi_file/omi_file_interface.dart';

class OmiFile implements IOmiFile {
  final File _file;

  OmiFile(String path) : _file = File(path);

  @override
  Future<File> append(String contents) async => await _file.writeAsString(contents, mode: FileMode.append);

  @override
  void appendSync(String contents) => _file.writeAsStringSync(contents, mode: FileMode.append);

  @override
  Future<File> create() async => await _file.create();

  @override
  void createSync() => _file.createSync();

  @override
  Future<FileSystemEntity> delete() async => await _file.delete();

  @override
  void deleteSync() => _file.deleteSync();

  @override
  Future<bool> exists() async=> await _file.exists(); 

  @override
  Future<DateTime> lastModified() async => await _file.lastModified();

  @override
  DateTime lastModifiedSync() => _file.lastModifiedSync();

  @override
  String get name => _file.uri.pathSegments.last;

  @override
  String get path => _file.path;

  @override
  Future<List<int>> readAsBytes() async => await _file.readAsBytes();

  @override
  List<int> readAsBytesSync() => _file.readAsBytesSync();

  @override
  Future<String> readAsString() async => await _file.readAsString();

  @override
  String readAsStringSync() => _file.readAsStringSync();

  @override
  Future<File> rename(String newName) async {
    final directory = _file.parent;
    final newPath = '${directory.path}/$newName';
    return await _file.rename(newPath);
  }

  @override
  File renameSync(String newName) {
    final directory = _file.parent;
    final newPath = '${directory.path}/$newName';
    return _file.renameSync(newPath);
  }

  @override
  int get size => _file.lengthSync();

  @override
  Future<File> writeAsBytes(List<int> bytes)async => await _file.writeAsBytes(bytes);

  @override
  void writeAsBytesSync(List<int> bytes) => _file.writeAsBytesSync(bytes);

  @override
  Future<File> writeAsString(String contents)async => await _file.writeAsString(contents);

  @override
  void writeAsStringSync(String contents) => _file.writeAsStringSync(contents);
}
