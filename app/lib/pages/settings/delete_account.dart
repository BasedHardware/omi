import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
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

/// Account deletion: reason → feedback → typed confirmation. Each step is its own route, so the
/// iOS edge swipe and system back step back one step. This widget is step 1 and owns the flow.
class DeleteAccount extends StatefulWidget {
  const DeleteAccount({super.key});

  @override
  State<DeleteAccount> createState() => _DeleteAccountState();
}

/// What the reader has entered so far, shared by the three steps.
class _DeleteAccountFlow {
  final exit = LeaveFlowExit();
  final details = TextEditingController();
  final confirm = TextEditingController();
  String? reason;

  String? get detailsText => details.text.trim().isNotEmpty ? details.text.trim() : null;

  void dispose() {
    details.dispose();
    confirm.dispose();
  }
}

class _DeleteAccountState extends State<DeleteAccount> {
  final _flow = _DeleteAccountFlow();

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

  @override
  Widget build(BuildContext context) {
    final reason = _flow.reason;
    return LeaveFlowStepScaffold(
      step: 0,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowReasonTitle,
      subtitle: context.l10n.deleteFlowReasonSubtitle,
      onPopInvoked: (didPop) {
        // Back button, system back and the edge swipe all leave through here.
        if (didPop && !_flow.exit.finished) {
          PlatformManager.instance.analytics.deleteAccountAbandoned(step: 1, reason: _flow.reason);
        }
      },
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
        onPressed: reason == null
            ? null
            : () {
                PlatformManager.instance.analytics.deleteAccountReasonSelected(reason: reason);
                routeToPage(context, _DeleteFeedbackStep(flow: _flow));
              },
      ),
    );
  }
}

class _DeleteFeedbackStep extends StatelessWidget {
  const _DeleteFeedbackStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  Widget build(BuildContext context) {
    void next() => routeToPage(context, _DeleteConfirmStep(flow: flow));
    return LeaveFlowStepScaffold(
      step: 1,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowFeedbackTitle,
      subtitle: context.l10n.deleteFlowFeedbackSubtitle,
      body: Align(
        alignment: Alignment.topCenter,
        child: SingleChildScrollView(
          child: LeaveFlowTextField(
            controller: flow.details,
            maxLength: 500,
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

    try {
      final ok = await deleteAccount(reason: _flow.reason, reasonDetails: details);
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
    return LeaveFlowStepScaffold(
      step: 2,
      stepCount: _stepCount,
      title: context.l10n.deleteFlowConfirmTitle,
      subtitle: context.l10n.deleteFlowConfirmSubtitle,
      canPop: !_isDeleting,
      body: Column(
        children: [
          LeaveFlowNotice(
            icon: FontAwesomeIcons.triangleExclamation,
            text: context.l10n.cannotBeUndone,
            color: OmiColors.danger,
          ),
          const SizedBox(height: OmiSpacing.md),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
              children: [
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.solidCommentDots, text: context.l10n.allDataErased),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.puzzlePiece, text: context.l10n.appsDisconnected),
                LeaveFlowConsequenceRow(
                  icon: FontAwesomeIcons.creditCard,
                  text: context.l10n.deleteConsequenceSubscription,
                ),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.fileArrowDown, text: context.l10n.exportBeforeDelete),
                // The row above promises an export; this is where it happens.
                ValueListenableBuilder<bool>(
                  valueListenable: DataExport.exportInProgress,
                  builder: (context, exporting, _) => OmiButton.secondary(
                    label: context.l10n.exportAllData,
                    leading: const FaIcon(FontAwesomeIcons.fileArrowDown),
                    size: OmiButtonSize.compact,
                    expand: true,
                    isLoading: exporting,
                    onPressed: _isDeleting ? null : () => DataExport.run(context),
                  ),
                ),
                const SizedBox(height: OmiSpacing.xs),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.ban, text: context.l10n.deleteConsequenceNoRecovery),
                const SizedBox(height: OmiSpacing.md),
                Text(
                  context.l10n.deleteTypeToConfirm,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: OmiSpacing.xs),
                TextField(
                  controller: _flow.confirm,
                  enabled: !_isDeleting,
                  textCapitalization: TextCapitalization.characters,
                  inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z]'))],
                  style: OmiType.callout.copyWith(fontWeight: FontWeight.w600, letterSpacing: 2),
                  decoration: leaveFlowInputDecoration(hint: confirmWord, focusColor: OmiColors.danger)
                      .copyWith(hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary, letterSpacing: 2)),
                ),
              ],
            ),
          ),
        ],
      ),
      actions: ValueListenableBuilder<TextEditingValue>(
        valueListenable: _flow.confirm,
        builder: (context, value, _) {
          final canDelete = !_isDeleting && value.text.trim().toUpperCase() == confirmWord;
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              OmiButton(
                label: context.l10n.keepMyAccount,
                expand: true,
                onPressed: _isDeleting
                    ? null
                    : () {
                        PlatformManager.instance.analytics.deleteAccountKeptAccount(step: 3, reason: _flow.reason);
                        _flow.exit.close(context);
                      },
              ),
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.destructive(
                label: context.l10n.deleteAccountTitle,
                expand: true,
                isLoading: _isDeleting,
                onPressed: canDelete || _isDeleting ? _confirmDelete : null,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Reason {
  final String key;
  final FaIconData icon;
  const _Reason(this.key, this.icon);
}
