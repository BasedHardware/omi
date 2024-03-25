import 'package:supabase_flutter/supabase_flutter.dart' hide Provider;
import "../../env/env.dart";

export 'database/database.dart';

const _kSupabaseUrl = Env.supabaseUrl;
const _kSupabaseAnonKey = Env.supabaseAnonKey;

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
