import 'package:friend_private/env/env.dart';
import 'package:friend_private/env/prod_env.dart';

import 'flavors.dart';
import 'main.dart' as runner;

Future<void> main() async {
  F.env = Environment.prod;
  Env.init(ProdEnv());
  runner.main();
}

// Run me with flutter run -t lib/main_prod.dart --flavor prod