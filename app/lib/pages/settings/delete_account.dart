import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/widgets/leave_flow_widgets.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/clear_user_state.dart';
import 'package:omi/utils/auth/clear_deleted_account_session.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/wal_file_manager.dart';

const _stepCount = 3;
const _detailsLength = 500;
const _confirmLength = 32;

/// The account deletion request; the backend API unless a test supplies an inert one.
typedef DeleteAccountRequest = Future<bool> Function({String? reason, String? reasonDetails});

/// Account deletion: reason → feedback → typed confirmation. Each step is its own route, so the
/// iOS edge swipe and system back step back one step. This widget is step 1 and owns the flow.
class DeleteAccount extends StatefulWidget {
  const DeleteAccount({super.key, @visibleForTesting this.deleteAccountRequest});

  /// Replaces the backend request in tests only.
  final DeleteAccountRequest? deleteAccountRequest;

  @override
  State<DeleteAccount> createState() => _DeleteAccountState();
}

/// What the reader has entered so far, shared by the three steps.
class _DeleteAccountFlow {
  _DeleteAccountFlow(this.request);

  final DeleteAccountRequest request;
  final exit = LeaveFlowExit();
  final details = TextEditingController();
  final confirm = TextEditingController();
  String? reason;

  String? get detailsText => details.text.trim().isNotEmpty ? details.text.trim() : null;

  /// Whether [confirm] holds the localized confirmation word; the same rule gates both renderers.
  bool confirmed(String word) => confirm.text.trim().toUpperCase() == word;

  void dispose() {
    details.dispose();
    confirm.dispose();
  }
}

class _DeleteAccountState extends State<DeleteAccount> {
  late final _flow = _DeleteAccountFlow(widget.deleteAccountRequest ?? deleteAccount);

  static const _reasons = [
    _Reason('privacy_concerns', FontAwesomeIcons.shield),
    _Reason('not_using_enough', FontAwesomeIcons.clock),
    _Reason('missing_features', FontAwesomeIcons.puzzlePiece),
    _Reason('technical_issues', FontAwesomeIcons.triangleExclamation),
    _Reason('found_alternative', FontAwesomeIcons.arrowRightArrowLeft),
    _Reason('taking_break', FontAwesomeIcons.mugHot),
    _Reason('other', FontAwesomeIcons.ellipsis),
  ];

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.deleteAccountFlowStarted();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _flow.exit.attach(context);
  }

  @override
  void dispose() {
    _flow.dispose();
    super.dispose();
  }

  String _label(String key) => switch (key) {
        'privacy_concerns' => context.l10n.deleteReasonPrivacy,
        'not_using_enough' => context.l10n.deleteReasonNotUsing,
        'missing_features' => context.l10n.deleteReasonMissingFeatures,
        'technical_issues' => context.l10n.deleteReasonTechnicalIssues,
        'found_alternative' => context.l10n.deleteReasonFoundAlternative,
        'taking_break' => context.l10n.deleteReasonTakingBreak,
        'other' => context.l10n.deleteReasonOther,
        _ => key,
      };

  void _onPopInvoked(bool didPop) {
    // Back button, system back and the edge swipe all leave through here.
    if (didPop && !_flow.exit.finished) {
      PlatformManager.instance.analytics.deleteAccountAbandoned(step: 1, reason: _flow.reason);
    }
  }

  void _continue() {
    final reason = _flow.reason;
    if (reason == null) return;
    PlatformManager.instance.analytics.deleteAccountReasonSelected(reason: reason);
    routeToPage(context, _DeleteFeedbackStep(flow: _flow));
  }

  @override
  Widget build(BuildContext context) {
    final reason = _flow.reason;
    final fallback = LeaveFlowStepScaffold(
      step: 0,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowReasonTitle,
      subtitle: context.l10n.deleteFlowReasonSubtitle,
      onPopInvoked: _onPopInvoked,
      body: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        itemCount: _reasons.length,
        separatorBuilder: (_, __) => const SizedBox(height: OmiSpacing.xs),
        itemBuilder: (_, i) => LeaveFlowReasonTile(
          icon: _reasons[i].icon,
          label: _label(_reasons[i].key),
          selected: reason == _reasons[i].key,
          onTap: () => setState(() => _flow.reason = _reasons[i].key),
        ),
      ),
      actions: OmiButton(
        label: context.l10n.continueButton,
        expand: true,
        onPressed: reason == null ? null : _continue,
      ),
    );
    return nativeLeaveStep(
      context,
      step: 0,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowReasonTitle,
      subtitle: context.l10n.deleteFlowReasonSubtitle,
      canPop: true,
      onPopInvoked: _onPopInvoked,
      fallback: fallback,
      sections: [
        NativeSection('delete_reasons', [
          for (final option in _reasons)
            NativeRow('delete_reason:${option.key}', _label(option.key),
                symbol: reason == option.key ? 'checkmark.circle.fill' : 'circle',
                action: (_) => setState(() => _flow.reason = option.key)),
        ]),
        NativeSection('delete_reason_actions', [
          NativeRow('leave_continue', context.l10n.continueButton, enabled: reason != null, action: (_) => _continue()),
        ]),
      ],
    );
  }
}

class _DeleteFeedbackStep extends StatelessWidget {
  const _DeleteFeedbackStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  Widget build(BuildContext context) {
    void next() => routeToPage(context, _DeleteConfirmStep(flow: flow));
    final fallback = LeaveFlowStepScaffold(
      step: 1,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowFeedbackTitle,
      subtitle: context.l10n.deleteFlowFeedbackSubtitle,
      body: Align(
        alignment: Alignment.topCenter,
        child: SingleChildScrollView(
          child: LeaveFlowTextField(
            controller: flow.details,
            maxLength: _detailsLength,
            hint: context.l10n.deleteFlowFeedbackHint,
          ),
        ),
      ),
      actions: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiButton(label: context.l10n.continueButton, expand: true, onPressed: next),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(label: context.l10n.skipForNow, expand: true, onPressed: next),
        ],
      ),
    );
    if (!nativePresentationEnabled) return fallback;
    // Rebuilds with every native edit, so the next snapshot carries the current text.
    return ListenableBuilder(
      listenable: flow.details,
      builder: (context, _) => nativeLeaveStep(
        context,
        step: 1,
        stepCount: _stepCount,
        title: context.l10n.deleteFlowFeedbackTitle,
        subtitle: context.l10n.deleteFlowFeedbackSubtitle,
        canPop: true,
        fallback: fallback,
        sections: [
          NativeSection('delete_feedback', [
            NativeRow('delete_details', context.l10n.deleteFlowFeedbackHint,
                kind: 'text',
                value: nativeLeaveText(flow.details.text, _detailsLength),
                maximumLength: _detailsLength,
                action: (value) => flow.details.text = value as String),
          ]),
          NativeSection('delete_feedback_actions', [
            NativeRow('leave_continue', context.l10n.continueButton, action: (_) {
              next();
            }),
            NativeRow('leave_skip', context.l10n.skipForNow, action: (_) {
              next();
            }),
          ]),
        ],
      ),
    );
  }
}

class _DeleteConfirmStep extends StatefulWidget {
  const _DeleteConfirmStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  State<_DeleteConfirmStep> createState() => _DeleteConfirmStepState();
}

class _DeleteConfirmStepState extends State<_DeleteConfirmStep> {
  bool _isDeleting = false;

  _DeleteAccountFlow get _flow => widget.flow;

  Future<void> _confirmDelete() async {
    FocusScope.of(context).unfocus();
    setState(() => _isDeleting = true);
    final details = _flow.detailsText;

    // The native view shows a blocking activity while the request runs; it closes before anything else.
    final activity = await leaveFlowActivity(context, context.l10n.deleting);
    try {
      final bool ok;
      try {
        ok = await _flow.request(reason: _flow.reason, reasonDetails: details);
      } finally {
        await activity?.dismiss();
      }
      if (!mounted) return;
      if (!ok) {
        OmiFeedback.error(context, context.l10n.deleteAccountFailed);
        setState(() => _isDeleting = false);
        return;
      }
      PlatformManager.instance.analytics.deleteAccountConfirmed();
      PlatformManager.instance.analytics.deleteAccountFeedbackSubmitted(
        reason: _flow.reason ?? 'unspecified',
        details: details,
      );
      PlatformManager.instance.analytics.deleteUser();
      _flow.exit.finished = true;
      await clearDeletedAccountSession(
        authService: AuthService.instance,
        clearUserState: () => clearAllUserState(context),
        clearWal: WalFileManager.clearAll,
        clearPreferences: SharedPreferencesUtil().clear,
      );
      if (!mounted) return;
      routeToPage(context, const AppShell(), replace: true);
    } catch (_) {
      if (!mounted) return;
      OmiFeedback.error(context, context.l10n.deleteAccountFailed);
      setState(() => _isDeleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final confirmWord = context.l10n.deleteConfirmationWord;
    void keep() {
      PlatformManager.instance.analytics.deleteAccountKeptAccount(step: 3, reason: _flow.reason);
      _flow.exit.close(context);
    }

    final fallback = LeaveFlowStepScaffold(
      step: 2,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowConfirmTitle,
      subtitle: context.l10n.deleteFlowConfirmSubtitle,
      canPop: !_isDeleting,
      // Irreversibility is said once, in the subtitle. The typed confirmation sits with the
      // buttons so it is never hidden behind them, and stays above the keyboard.
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        children: [
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.solidCommentDots),
                title: context.l10n.allDataErased,
              ),
              OmiSettingsRow(leading: const FaIcon(FontAwesomeIcons.puzzlePiece), title: context.l10n.appsDisconnected),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.creditCard),
                title: context.l10n.deleteConsequenceSubscription,
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiSettingsGroup(
            children: [
              ValueListenableBuilder<bool>(
                valueListenable: DataExport.exportInProgress,
                builder: (context, exporting, _) => OmiSettingsRow(
                  key: const Key('delete_account_export_row'),
                  leading: const FaIcon(FontAwesomeIcons.fileArrowDown),
                  title: context.l10n.exportAllData,
                  trailing: exporting ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
                  showChevron: !exporting,
                  onTap: _isDeleting || exporting ? null : () => DataExport.run(context),
                ),
              ),
            ],
          ),
        ],
      ),
      actions: ValueListenableBuilder<TextEditingValue>(
        valueListenable: _flow.confirm,
        builder: (context, value, _) {
          final canDelete = !_isDeleting && _flow.confirmed(confirmWord);
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                context.l10n.deleteTypeToConfirm,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: OmiSpacing.xs),
              TextField(
                key: const Key('delete_account_confirm_field'),
                controller: _flow.confirm,
                enabled: !_isDeleting,
                textCapitalization: TextCapitalization.characters,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z]'))],
                style: OmiType.callout.copyWith(fontWeight: FontWeight.w600, letterSpacing: 2),
                decoration: leaveFlowInputDecoration(
                  hint: confirmWord,
                  focusColor: OmiColors.danger,
                ).copyWith(hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary, letterSpacing: 2)),
              ),
              const SizedBox(height: OmiSpacing.md),
              // Delete is the primary once the word is typed; until then Keep is the only live action.
              OmiButton.destructive(
                label: context.l10n.deleteAccountTitle,
                expand: true,
                isLoading: _isDeleting,
                onPressed: canDelete || _isDeleting ? _confirmDelete : null,
              ),
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                label: context.l10n.keepMyAccount,
                expand: true,
                onPressed: _isDeleting ? null : keep,
              ),
            ],
          );
        },
      ),
    );
    if (!nativePresentationEnabled) return fallback;
    final l10n = context.l10n;
    // Export availability follows the shared export owner, exactly like the fallback's row.
    return ValueListenableBuilder<bool>(
      valueListenable: DataExport.exportInProgress,
      builder: (context, exporting, _) => nativeLeaveStep(
        context,
        step: 2,
        stepCount: _stepCount,
        title: l10n.deleteFlowConfirmTitle,
        subtitle: l10n.deleteFlowConfirmSubtitle,
        canPop: !_isDeleting,
        fallback: fallback,
        sections: [
          NativeSection('delete_consequences', [
            NativeRow('delete_all_data', l10n.allDataErased, kind: 'label', symbol: 'text.bubble'),
            NativeRow('delete_apps', l10n.appsDisconnected, kind: 'label', symbol: 'puzzlepiece'),
            NativeRow('delete_subscription', l10n.deleteConsequenceSubscription, kind: 'label', symbol: 'creditcard'),
          ]),
          NativeSection('delete_export_section', [
            NativeRow('delete_export', l10n.exportAllData,
                symbol: 'square.and.arrow.down',
                subtitle: exporting ? l10n.exportingAllData : '',
                enabled: !_isDeleting && !exporting,
                action: (_) => DataExport.run(context)),
          ]),
          // The field shows what was typed; Delete stays disabled until Dart finds the exact word.
          NativeSection(
              'delete_confirmation',
              [
                NativeRow('delete_confirm_word', confirmWord,
                    kind: 'text',
                    value: nativeLeaveText(_flow.confirm.text, _confirmLength),
                    maximumLength: _confirmLength,
                    enabled: !_isDeleting,
                    action: (value) => setState(() => _flow.confirm.text = value as String)),
                NativeRow('delete_account', l10n.deleteAccountTitle,
                    destructive: true, enabled: !_isDeleting && _flow.confirmed(confirmWord), action: (_) async {
                  if (!_isDeleting && _flow.confirmed(confirmWord)) await _confirmDelete();
                }),
                NativeRow('delete_keep', l10n.keepMyAccount, enabled: !_isDeleting, action: (_) => keep()),
              ],
              title: l10n.deleteTypeToConfirm),
        ],
      ),
    );
  }
}

class _Reason {
  final String key;
  final FaIconData icon;
  const _Reason(this.key, this.icon);
}
