import 'package:firebase_auth/firebase_auth.dart';

Future<UserCredential?> anonymousSignInFunc() =>
    FirebaseAuth.instance.signInAnonymously();
