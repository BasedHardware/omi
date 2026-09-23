import 'experiment_definition.dart';

enum SummaryFeedbackLayout { standard, compact }

/// Add reviewed presentation definitions here, with matching operational specs
/// in app/docs/experiments. Shipping a definition does not activate its flag.
abstract final class MobileExperiments {
  static final summaryFeedbackLayout = ExperimentDefinition<SummaryFeedbackLayout>(
    key: 'mobile-summary-feedback-layout-v1',
    version: 1,
    variants: {'control': SummaryFeedbackLayout.standard, 'compact': SummaryFeedbackLayout.compact},
    defaultVariant: 'control',
    namespaces: {'mobile-prod', 'mobile-dev'},
    surfaces: {'summary-feedback'},
    expiresAt: DateTime.utc(2027, 1, 1),
  );
  static final List<ExperimentDefinition<dynamic>> all = List.unmodifiable([summaryFeedbackLayout]);
}
