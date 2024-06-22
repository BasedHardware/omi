import 'env/dev_env.dart';
import 'env/env.dart';
import 'flavors.dart';
import 'main.dart' as runner;

Future<void> main() async {
  F.env = Environment.dev;
  Env.init(DevEnv());
  runner.main();
}

// Run me with flutter run -t lib/main_dev.dart --flavor dev