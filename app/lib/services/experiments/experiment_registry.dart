import 'experiment_definition.dart';

/// Add reviewed presentation definitions here, with matching operational specs
/// in app/docs/experiments. Shipping a definition does not activate its flag.
abstract final class MobileExperiments {
  static final List<ExperimentDefinition<dynamic>> all = List.unmodifiable(const <ExperimentDefinition<dynamic>>[]);
}
