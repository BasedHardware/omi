
abstract class IOmiFile {
  String get path;
  String get name;
  int get size;

  Future<bool> exists();  
  Future<void> create();
  Future<void> delete();
  Future<void> writeAsString(String contents);
  Future<String> readAsString();
  Future<void> append(String contents);
  Future<void> rename(String newName);
  Future<DateTime> lastModified();

  
  Future<void> writeAsBytes(List<int> bytes);
  Future<List<int>> readAsBytes();

  void createSync();
  void deleteSync();
  void writeAsStringSync(String contents);
  String readAsStringSync();
  void appendSync(String contents);
  void renameSync(String newName);
  DateTime lastModifiedSync();

  
  void writeAsBytesSync(List<int> bytes);
  List<int> readAsBytesSync();
}
