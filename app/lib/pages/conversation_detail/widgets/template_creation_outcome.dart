/// Terminal outcomes of the quick-template creation flow, classified by whether
/// the user should see a success or an error message.
///
/// #10074/#10100: a template that was created on the server but whose install
/// did not stick must be surfaced as an error — never reported as a successful
/// install. The sheet derives its snackbar polarity from
/// [templateCreationOutcomeIsError] so that regression cannot be silently
/// reintroduced (it is the one place this decision lives, and it is tested).
enum TemplateCreationOutcome {
  /// The create/submit call itself failed; nothing was created.
  submitFailed,

  /// App created and installed — full success.
  installed,

  /// App created but the install did not stick — must read as a failure.
  installFailed,

  /// App created; no install was attempted (its details could not be
  /// fetched) — a partial success, not a failure.
  createdWithoutInstall,
}

/// Whether [outcome] must be shown to the user as an error rather than success.
bool templateCreationOutcomeIsError(TemplateCreationOutcome outcome) {
  switch (outcome) {
    case TemplateCreationOutcome.submitFailed:
    case TemplateCreationOutcome.installFailed:
      return true;
    case TemplateCreationOutcome.installed:
    case TemplateCreationOutcome.createdWithoutInstall:
      return false;
  }
}
