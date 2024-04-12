import '../database.dart';

class RecordsTable extends SupabaseTable<RecordsRow> {
  @override
  String get tableName => 'records';

  @override
  RecordsRow createRow(Map<String, dynamic> data) => RecordsRow(data);
}

class RecordsRow extends SupabaseDataRow {
  RecordsRow(super.data);

  @override
  SupabaseTable get table => RecordsTable();

  int get id => getField<int>('id')!;
  set id(int value) => setField<int>('id', value);

  DateTime get createdAt => getField<DateTime>('created_at')!;
  set createdAt(DateTime value) => setField<DateTime>('created_at', value);

  String? get rawText => getField<String>('raw_text');
  set rawText(String? value) => setField<String>('raw_text', value);

  String? get embeddings => getField<String>('embeddings');
  set embeddings(String? value) => setField<String>('embeddings', value);
}
