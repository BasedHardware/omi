import 'package:supabase_flutter/supabase_flutter.dart' hide Provider;

export 'database/database.dart';

const _kSupabaseUrl = 'https://zimavzhsuyykrvtgxghi.supabase.co';
const _kSupabaseAnonKey =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InppbWF2emhzdXl5a3J2dGd4Z2hpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg0NzM4MTYsImV4cCI6MjAyNDA0OTgxNn0.3CblX62qbHOK-tUTX0SgeLj2sntFlKXc7KXr1yugyts';

class SupaFlow {
  SupaFlow._();

  static SupaFlow? _instance;
  static SupaFlow get instance => _instance ??= SupaFlow._();

  final _supabase = Supabase.instance.client;
  static SupabaseClient get client => instance._supabase;

  static Future initialize() => Supabase.initialize(
        url: _kSupabaseUrl,
        anonKey: _kSupabaseAnonKey,
        debug: false,
      );
}
