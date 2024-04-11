import 'package:envied/envied.dart';
part 'env.g.dart';

@Envied(path: '.env')
abstract class Env {
  // OpenAI
  @EnviedField(varName: 'OPENAI_API_KEY')
  static const String openAIApiKey = _Env.openAIApiKey;

  // Pinecone
  @EnviedField(varName: 'PINECONE_API_KEY')
  static const String pineconeApiKey = _Env.pineconeApiKey;

  // Firebase
  @EnviedField(varName: 'FIREBASE_API_KEY')
  static const String firebaseApiKey = _Env.firebaseApiKey;
  @EnviedField(varName: 'FIREBASE_AUTH_DOMAIN')
  static const String firebaseAuthDomain = _Env.firebaseAuthDomain;
  @EnviedField(varName: 'FIREBASE_PROJECT_ID')
  static const String firebaseProjectId = _Env.firebaseProjectId;
  @EnviedField(varName: 'FIREBASE_STORAGE_BUCKET')
  static const String firebaseStorageBucket = _Env.firebaseStorageBucket;
  @EnviedField(varName: 'FIREBASE_MESSAGE_SENDER_ID')
  static const String firebaseMessageSenderId = _Env.firebaseMessageSenderId;
  @EnviedField(varName: 'FIREBASE_APP_ID')
  static const String firebaseAppId = _Env.firebaseAppId;
  @EnviedField(varName: 'FIREBASE_MEASUREMENT_ID')
  static const String firebaseMeasurementId = _Env.firebaseMeasurementId;

  // Supabase
  @EnviedField(varName: 'SUPABASE_URL')
  static const String supabaseUrl = _Env.supabaseUrl;
  @EnviedField(varName: 'SUPABASE_ANON_KEY')
  static const String supabaseAnonKey = _Env.supabaseAnonKey;
}
