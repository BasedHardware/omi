import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// Full-screen 3-step account deletion flow.
class DeleteAccount extends StatefulWidget {
  const DeleteAccount({super.key});

  @override
  State<DeleteAccount> createState() => _DeleteAccountState();
}

class _DeleteAccountState extends State<DeleteAccount> {
  final PageController _pageController = PageController();
  final TextEditingController _detailsController = TextEditingController();
  final TextEditingController _confirmController = TextEditingController();

  String? _selectedReason;
  int _page = 0;
  bool _isDeleting = false;

  @override
  void initState() {
    super.initState();
    MixpanelManager().deleteAccountFlowStarted();
    _confirmController.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _pageController.dispose();
    _detailsController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  static const _reasons = [
    _Reason('privacy_concerns', FontAwesomeIcons.shield),
    _Reason('not_using_enough', FontAwesomeIcons.clock),
    _Reason('missing_features', FontAwesomeIcons.puzzlePiece),
    _Reason('technical_issues', FontAwesomeIcons.triangleExclamation),
    _Reason('found_alternative', FontAwesomeIcons.arrowRightArrowLeft),
    _Reason('taking_break', FontAwesomeIcons.mugHot),
    _Reason('other', FontAwesomeIcons.ellipsis),
  ];

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

  void _next() {
    if (_page < 2) {
      _pageController.nextPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      setState(() => _page++);
    }
  }

  void _back() {
    if (_isDeleting) return;
    if (_page > 0) {
      _pageController.previousPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      setState(() => _page--);
    } else {
      // Tracking happens in onPopInvokedWithResult so AppBar back and
      // system back/swipe go through the same code path.
      Navigator.of(context).pop();
    }
  }

  Future<void> _confirmDelete() async {
    FocusScope.of(context).unfocus();
    setState(() => _isDeleting = true);
    final details = _detailsController.text.trim().isNotEmpty ? _detailsController.text.trim() : null;

    try {
      final ok = await deleteAccount(reason: _selectedReason, reasonDetails: details);
      if (!mounted) return;
      if (!ok) {
        AppSnackbar.showSnackbarError(context.l10n.deleteAccountFailed);
        setState(() => _isDeleting = false);
        return;
      }
      MixpanelManager().deleteAccountConfirmed();
      MixpanelManager().deleteAccountFeedbackSubmitted(reason: _selectedReason ?? 'unspecified', details: details);
      MixpanelManager().deleteUser();
      await WalFileManager.clearAll();
      await SharedPreferencesUtil().clear();
      await FirebaseAuth.instance.signOut();
      if (!mounted) return;
      routeToPage(context, const AppShell(), replace: true);
    } catch (_) {
      if (!mounted) return;
      AppSnackbar.showSnackbarError(context.l10n.deleteAccountFailed);
      setState(() => _isDeleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _page == 0 && !_isDeleting,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) {
          // Native swipe/back on page 0 still counts as an abandon.
          MixpanelManager().deleteAccountAbandoned(step: _page + 1, reason: _selectedReason);
          return;
        }
        if (!_isDeleting) _back();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios, size: 18),
              onPressed: _isDeleting ? null : _back,
            ),
            title: _stepIndicator(),
            centerTitle: true,
          ),
          body: PageView(
            controller: _pageController,
            physics: const NeverScrollableScrollPhysics(),
            children: [_stepReason(), _stepFeedback(), _stepConfirm()],
          ),
        ),
      ),
    );
  }

  Widget _stepIndicator() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (i) {
        final active = i <= _page;
        return Container(
          width: i == _page ? 24 : 8,
          height: 4,
          margin: const EdgeInsets.symmetric(horizontal: 3),
          decoration: BoxDecoration(
            color: active ? Colors.white : Colors.grey.shade800,
            borderRadius: BorderRadius.circular(2),
          ),
        );
      }),
    );
  }

  // ─── Step 1: Reason ───

  Widget _stepReason() {
    final canContinue = _selectedReason != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.deleteFlowReasonTitle,
                style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              Text(context.l10n.deleteFlowReasonSubtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            itemCount: _reasons.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (_, i) => _reasonTile(_reasons[i]),
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
            child: SizedBox(
              width: double.infinity,
              height: 52,
              child: ElevatedButton(
                onPressed: canContinue
                    ? () {
                        MixpanelManager().deleteAccountReasonSelected(reason: _selectedReason!);
                        _next();
                      }
                    : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  disabledBackgroundColor: Colors.grey.shade900,
                  foregroundColor: Colors.black,
                  disabledForegroundColor: Colors.grey.shade700,
                  elevation: 0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                child: Text(
                  context.l10n.continueButton,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _reasonTile(_Reason reason) {
    final selected = _selectedReason == reason.key;
    return GestureDetector(
      onTap: () => setState(() => _selectedReason = reason.key),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: selected ? Colors.grey.shade900 : Colors.grey.shade900.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: selected ? Colors.grey.shade600 : Colors.grey.shade800),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: selected ? Colors.grey.shade800 : Colors.grey.shade800.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: FaIcon(reason.icon, size: 14, color: selected ? Colors.white : Colors.grey.shade600),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                _label(reason.key),
                style: TextStyle(color: selected ? Colors.white : Colors.grey.shade400, fontSize: 15),
              ),
            ),
            Icon(
              selected ? Icons.check_circle_rounded : Icons.circle_outlined,
              size: 22,
              color: selected ? Colors.white : Colors.grey.shade700,
            ),
          ],
        ),
      ),
    );
  }

  // ─── Step 2: Feedback ───

  Widget _stepFeedback() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.deleteFlowFeedbackTitle,
                style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              Text(
                context.l10n.deleteFlowFeedbackSubtitle,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 15),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: TextField(
            controller: _detailsController,
            maxLines: 5,
            maxLength: 500,
            style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.5),
            decoration: InputDecoration(
              hintText: context.l10n.deleteFlowFeedbackHint,
              hintStyle: TextStyle(color: Colors.grey.shade700, fontSize: 14),
              filled: true,
              fillColor: Colors.grey.shade900.withValues(alpha: 0.5),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: Colors.grey.shade800),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: Colors.grey.shade800),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: Colors.grey.shade600),
              ),
              counterStyle: TextStyle(color: Colors.grey.shade700),
              contentPadding: const EdgeInsets.all(16),
            ),
          ),
        ),
        const Spacer(),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
            child: Column(
              children: [
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: _next,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      elevation: 0,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    child: Text(
                      context.l10n.continueButton,
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                GestureDetector(
                  onTap: _next,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    child: Text(context.l10n.skipForNow, style: TextStyle(color: Colors.grey.shade600, fontSize: 15)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ─── Step 3: Final confirmation ───

  Widget _stepConfirm() {
    final confirmWord = context.l10n.deleteConfirmationWord;
    final canDelete = !_isDeleting && _confirmController.text.trim().toUpperCase() == confirmWord;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.deleteFlowConfirmTitle,
                style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              Text(context.l10n.deleteFlowConfirmSubtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.red.shade900.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.red.shade800.withValues(alpha: 0.3)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: FaIcon(FontAwesomeIcons.triangleExclamation, size: 14, color: Colors.red.shade300),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    context.l10n.cannotBeUndone,
                    style: TextStyle(color: Colors.red.shade200, fontSize: 13, height: 1.5),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            children: [
              _featureRow(FontAwesomeIcons.solidCommentDots, context.l10n.allDataErased),
              _featureRow(FontAwesomeIcons.puzzlePiece, context.l10n.appsDisconnected),
              _featureRow(FontAwesomeIcons.creditCard, context.l10n.deleteConsequenceSubscription),
              _featureRow(FontAwesomeIcons.fileArrowDown, context.l10n.exportBeforeDelete),
              _featureRow(FontAwesomeIcons.ban, context.l10n.deleteConsequenceNoRecovery),
              const SizedBox(height: 16),
              Text(
                context.l10n.deleteTypeToConfirm,
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _confirmController,
                enabled: !_isDeleting,
                textCapitalization: TextCapitalization.characters,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z]'))],
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 2,
                ),
                decoration: InputDecoration(
                  hintText: confirmWord,
                  hintStyle: TextStyle(color: Colors.grey.shade700, letterSpacing: 2),
                  filled: true,
                  fillColor: Colors.grey.shade900.withValues(alpha: 0.5),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: Colors.grey.shade800),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: Colors.grey.shade800),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: Colors.red.shade600),
                  ),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                ),
              ),
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
            child: Column(
              children: [
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: _isDeleting
                        ? null
                        : () {
                            MixpanelManager().deleteAccountKeptAccount(step: 3, reason: _selectedReason);
                            Navigator.of(context).pop();
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      elevation: 0,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    child: Text(
                      context.l10n.keepMyAccount,
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                GestureDetector(
                  onTap: canDelete ? _confirmDelete : null,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    child: _isDeleting
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.grey),
                          )
                        : Text(
                            context.l10n.deleteAccountPermanently,
                            style: TextStyle(
                              color: canDelete ? Colors.red.shade400 : Colors.grey.shade700,
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _featureRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: Colors.grey.shade900.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.grey.shade800),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: Colors.grey.shade800.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(child: FaIcon(icon, size: 14, color: Colors.grey.shade500)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(text, style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.3)),
            ),
          ],
        ),
      ),
    );
  }
}

class _Reason {
  final String key;
  final IconData icon;
  const _Reason(this.key, this.icon);
}
