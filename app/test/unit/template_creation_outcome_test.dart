import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversation_detail/widgets/template_creation_outcome.dart';

/// #10074/#10100 regression pin: the quick-template sheet derives its
/// success/error snackbar polarity from templateCreationOutcomeIsError, so a
/// created-but-not-installed template can never again be reported as a
/// successful install. #10100 fixed the behavior but shipped without this pin
/// (the decision was inline in the widget, untestable without a full widget
/// harness); this closes that gap by making the decision a pure function.
void main() {
  test('a created-but-failed install is an error, never a success (#10074)', () {
    expect(templateCreationOutcomeIsError(TemplateCreationOutcome.installFailed), isTrue);
  });

  test('a full install is a success', () {
    expect(templateCreationOutcomeIsError(TemplateCreationOutcome.installed), isFalse);
  });

  test('created-without-install is a partial success, not an error', () {
    expect(templateCreationOutcomeIsError(TemplateCreationOutcome.createdWithoutInstall), isFalse);
  });

  test('a failed submit is an error', () {
    expect(templateCreationOutcomeIsError(TemplateCreationOutcome.submitFailed), isTrue);
  });

  test('every outcome is classified (exhaustive, no unhandled case)', () {
    for (final outcome in TemplateCreationOutcome.values) {
      // Must not throw; the switch is exhaustive by construction.
      templateCreationOutcomeIsError(outcome);
    }
    // Exactly the two failure outcomes read as errors.
    final errors = TemplateCreationOutcome.values.where(templateCreationOutcomeIsError).toSet();
    expect(errors, {TemplateCreationOutcome.submitFailed, TemplateCreationOutcome.installFailed});
  });
}
