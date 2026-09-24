/// Omi's mobile design system: tokens, theme, and the shared controls every page is built from.
///
/// `import 'package:omi/ui/ui.dart';` and reach for these before drawing anything by hand:
///
/// | Need | Use |
/// |---|---|
/// | Colour, type, radius, spacing, motion, haptics | `OmiColors`, `OmiType`, `OmiRadius`, `OmiSpacing`, `OmiMotion.of(context)`, `OmiHaptics` |
/// | A pushed page | `Scaffold(appBar: AppBar(leading: const OmiBackButton(), title: Text(...)))` — the theme gives the black bar, centred 17pt title, white icons |
/// | Leaving a modal (sheet, full-screen dialog, viewer) | trailing `OmiCloseButton` |
/// | A bottom sheet | `showOmiSheet(context:, title:, builder:)`; an editing sheet `showOmiEditSheet` |
/// | A row's long-press menu | `showOmiRowMenu(context, title:, actions:)` |
/// | A text action | `OmiButton` (`.secondary`, `.destructive`, `.tertiary`; `size: OmiButtonSize.compact`) |
/// | An icon-only action | `OmiIconButton(icon:, label:, onPressed:)` / `OmiIconButton.filled` |
/// | A spinner | `OmiSpinner` |
/// | Empty / failed / first-load page body | `OmiEmptyState`, `OmiErrorState`, `OmiLoadingState` |
/// | Settings | `OmiSettingsGroup` of `OmiSettingsRow` / `OmiSettingsRow.toggle`, `OmiSectionHeader`, `OmiSwitch` |
/// | Search | `OmiSearchField(placeholder:)` |
/// | Confirm / alert | `showOmiConfirm`, `showOmiConfirmWithOptOut`, `showOmiAlert` |
/// | Toasts, undo, copy | `OmiFeedback.confirm/info/error/undo`, `OmiClipboard.copy` |
/// | Dates, durations, speaker names | `OmiDateFormat.of(context)`, `OmiDuration`, `SpeakerNames` |
/// | Startup / background prompts | `PromptQueue.instance.enqueue` |
/// | A permission pre-prompt (reason, Allow, Open Settings) | `OmiPermissionRow` |
/// | A `Route` object | `omiPageRoute(builder:)`; to push a page use `routeToPage` |
///
/// Page backgrounds are `OmiColors.surface0` (also the scaffold default); never read
/// `Theme.of(context).colorScheme.primary` as a background — `primary` is the white accent.
library;

export 'components/omi_button.dart';
export 'components/omi_edit_sheet.dart';
export 'components/omi_icon_button.dart';
export 'components/omi_nav_buttons.dart';
export 'components/omi_page_states.dart';
export 'components/omi_permission_row.dart';
export 'components/omi_row_menu.dart';
export 'components/omi_search_field.dart';
export 'components/omi_settings.dart';
export 'components/omi_sheet.dart';
export 'components/omi_spinner.dart';
export 'feedback/omi_clipboard.dart';
export 'feedback/omi_dialogs.dart';
export 'feedback/omi_feedback.dart';
export 'format/omi_date_format.dart';
export 'format/omi_duration.dart';
export 'format/speaker_names.dart';
export 'omi_routes.dart';
export 'prompts/prompt_queue.dart';
export 'omi_theme.dart';
export 'omi_tokens.dart';
