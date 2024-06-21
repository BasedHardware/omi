import 'flavors.dart';
import 'main.dart' as runner;

Future<void> main() async {
  F.env = Environment.prod;
  runner.main();
}
