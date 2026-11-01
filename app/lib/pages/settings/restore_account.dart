import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/account_deletion.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/auth/finish_account_deletion.dart';

class RestoreAccount extends StatefulWidget {
  const RestoreAccount({
    super.key,
    required this.status,
    required this.onRestored,
    required this.onFinished,
    this.restore,
    this.finish,
  });

  final AccountDeletionStatus status;
  final VoidCallback onRestored;
  final VoidCallback onFinished;
  final Future<ApiResult<bool>> Function()? restore;
  final Future<ApiResult<bool>> Function()? finish;

  @override
  State<RestoreAccount> createState() => _RestoreAccountState();
}

class _RestoreAccountState extends State<RestoreAccount> {
  bool _busy = false;
  bool _restoring = true;
  bool _confirmFinish = false;

  Future<void> _act(bool restoring) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _restoring = restoring;
    });
    try {
      final result = restoring
          ? await (widget.restore ?? const AccountDeletionApi().restore)()
          : await (widget.finish ?? const AccountDeletionApi().finishDeleting)();
      if (!mounted) return;
      if (result case ApiSuccess<bool>(data: true)) {
        if (restoring) {
          widget.onRestored();
        } else {
          await clearFinishedDeletion(context);
          if (mounted) widget.onFinished();
        }
      } else {
        OmiFeedback.error(context, restoring ? context.l10n.somethingWentWrong : context.l10n.deleteAccountFailed);
      }
    } catch (_) {
      if (mounted) {
        OmiFeedback.error(context, restoring ? context.l10n.somethingWentWrong : context.l10n.deleteAccountFailed);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _confirmFinishDeleting() {
    final label = context.l10n.deleteFinishNowButton;
    _showFinishConfirmation().catchError((Object error, StackTrace stack) {
      OmiButton.reportOnPressedError(error, stack, label: label);
    });
  }

  Future<void> _showFinishConfirmation() async {
    if (_busy) return;
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteFinishNowTitle,
      message: context.l10n.deleteFinishNowWarning,
      confirmLabel: context.l10n.deleteFinishNowButton,
      destructive: true,
    );
    if (confirmed && mounted) await _act(false);
  }

  @override
  Widget build(BuildContext context) {
    final remaining = widget.status.restoreDaysRemainingAt(DateTime.now());
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: OmiSpacing.xl),
              Text(context.l10n.deleteRestoreTitle, style: OmiType.title2),
              const SizedBox(height: OmiSpacing.sm),
              Text(context.l10n.deleteRestoreSubtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              const SizedBox(height: OmiSpacing.lg),
              Expanded(
                child: ListView(
                  children: [
                    OmiSettingsGroup(children: [
                      OmiSettingsRow(title: context.l10n.deleteRestoreKeepData),
                      OmiSettingsRow(title: context.l10n.deleteRestoreBillingNotice),
                    ]),
                    const SizedBox(height: OmiSpacing.md),
                    if (remaining.available) ...[
                      Text(
                        remaining.days == 0
                            ? context.l10n.deleteRestoreLessThanDayRemaining
                            : context.l10n.deleteRestoreDaysRemaining(remaining.days),
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ],
                ),
              ),
              OmiButton(
                key: const Key('restore_my_account'),
                label: context.l10n.deleteRestoreButton,
                expand: true,
                isLoading: _busy && _restoring,
                onPressed: _busy ? null : () => _act(true),
              ),
              const SizedBox(height: OmiSpacing.xs),
              if (_confirmFinish)
                OmiButton.destructive(
                  key: const Key('finish_deleting_confirm'),
                  isLoading: _busy && !_restoring,
                  label: context.l10n.deleteFinishNowButton,
                  expand: true,
                  onPressed: _busy ? null : _confirmFinishDeleting,
                )
              else
                OmiButton.secondary(
                  key: const Key('finish_deleting'),
                  label: context.l10n.deleteFinishButton,
                  expand: true,
                  onPressed: _busy ? null : () => setState(() => _confirmFinish = true),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Construct product widgets only after status is known. Older endpoints are
/// supported, while network failures remain retryable rather than masquerading as active accounts.
class AccountDeletionGate extends StatefulWidget {
  const AccountDeletionGate(
      {super.key,
      required this.check,
      required this.productBuilder,
      required this.onFinished,
      required this.onRestored});
  final Future<ApiResult<AccountDeletionStatus>> Function({bool refresh}) check;
  final WidgetBuilder productBuilder;
  final VoidCallback onFinished;
  final VoidCallback onRestored;

  @override
  State<AccountDeletionGate> createState() => _AccountDeletionGateState();
}

class _AccountDeletionGateState extends State<AccountDeletionGate> {
  late Future<ApiResult<AccountDeletionStatus>> _status = widget.check();

  Future<void> _retry() async {
    final next = widget.check(refresh: true);
    setState(() {
      _status = next;
    });
    final result = await next;
    if (!mounted) return;
    // Restart shell initialization too: its first attempt may have stopped
    // behind the unavailable status, before loading any product providers.
    if (result case ApiSuccess<AccountDeletionStatus>(data: final status) when !status.pendingDeletion) {
      widget.onRestored();
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<ApiResult<AccountDeletionStatus>>(
        future: _status,
        builder: (context, snapshot) {
          final result = snapshot.data;
          if (result case ApiSuccess<AccountDeletionStatus>(:final data)) {
            if (!data.pendingDeletion) return widget.productBuilder(context);
            return RestoreAccount(
              status: data,
              onRestored: () {
                _status = widget.check(refresh: true);
                widget.onRestored();
              },
              onFinished: widget.onFinished,
            );
          }
          return Scaffold(
            backgroundColor: OmiColors.surface0,
            body: snapshot.connectionState != ConnectionState.done
                ? const OmiLoadingState()
                : OmiErrorState(
                    key: const Key('deletion_status_retry'),
                    message: context.l10n.somethingWentWrong,
                    onRetry: _retry,
                  ),
          );
        },
      );
}
