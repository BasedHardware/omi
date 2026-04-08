import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Full-screen 3-step cancellation flow shown as a page (not a sheet).
class CancelSubscriptionFlow extends StatefulWidget {
  const CancelSubscriptionFlow({super.key});

  static Future<bool?> show(BuildContext context) {
    return Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const CancelSubscriptionFlow()),
    );
  }

  @override
  State<CancelSubscriptionFlow> createState() => _CancelSubscriptionFlowState();
}

class _CancelSubscriptionFlowState extends State<CancelSubscriptionFlow> {
  final PageController _pageController = PageController();
  String? _selectedReason;
  final TextEditingController _detailsController = TextEditingController();
  bool _isCancelling = false;
  int _page = 0;

  @override
  void initState() {
    super.initState();
    MixpanelManager().subscriptionCancelFlowStarted();
  }

  static const _reasons = [
    _Reason('too_expensive', FontAwesomeIcons.wallet),
    _Reason('not_using_enough', FontAwesomeIcons.clock),
    _Reason('missing_features', FontAwesomeIcons.puzzlePiece),
    _Reason('audio_quality', FontAwesomeIcons.microphone),
    _Reason('battery_drain', FontAwesomeIcons.batteryQuarter),
    _Reason('found_alternative', FontAwesomeIcons.arrowRightArrowLeft),
    _Reason('other', FontAwesomeIcons.ellipsis),
  ];

  String _label(String key) => switch (key) {
        'too_expensive' => context.l10n.cancelReasonTooExpensive,
        'not_using_enough' => context.l10n.cancelReasonNotUsing,
        'missing_features' => context.l10n.cancelReasonMissingFeatures,
        'audio_quality' => context.l10n.cancelReasonAudioQuality,
        'battery_drain' => context.l10n.cancelReasonBatteryDrain,
        'found_alternative' => context.l10n.cancelReasonFoundAlternative,
        'other' => context.l10n.cancelReasonOther,
        _ => key,
      };

  @override
  void dispose() {
    _pageController.dispose();
    _detailsController.dispose();
    super.dispose();
  }

  void _next() {
    if (_page < 2) {
      _pageController.nextPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      setState(() => _page++);
    }
  }

  void _back() {
    if (_page > 0) {
      _pageController.previousPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      setState(() => _page--);
    } else {
      MixpanelManager().subscriptionCancelAbandoned(step: _page + 1, reason: _selectedReason);
      Navigator.of(context).pop(false);
    }
  }

  Future<void> _confirmCancel() async {
    setState(() => _isCancelling = true);
    final provider = context.read<UsageProvider>();
    final details = _detailsController.text.trim().isNotEmpty ? _detailsController.text.trim() : null;
    MixpanelManager().subscriptionCancelConfirmed(reason: _selectedReason!, details: details);

    try {
      final success = await provider.cancelUserSubscription(reason: _selectedReason, reasonDetails: details);
      if (mounted) {
        if (success) {
          AppSnackbar.showSnackbar(context.l10n.subscriptionSetToCancel);
          Navigator.of(context).pop(true);
        } else {
          AppSnackbar.showSnackbarError(context.l10n.failedToCancelSubscription);
          setState(() => _isCancelling = false);
        }
      }
    } catch (e) {
      if (mounted) {
        AppSnackbar.showSnackbarError(context.l10n.anErrorOccurredTryAgain);
        setState(() => _isCancelling = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _page == 0 && !_isCancelling,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _page > 0 && !_isCancelling) _back();
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
              onPressed: _isCancelling ? null : _back,
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

  // ─── Step 1: Pick a reason ───

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
              Text(context.l10n.whyAreYouCanceling,
                  style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(context.l10n.cancelReasonSubtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
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
                        MixpanelManager().subscriptionCancelReasonSelected(reason: _selectedReason!);
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
                child: Text(context.l10n.continueButton,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
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
              child: Text(_label(reason.key),
                  style: TextStyle(color: selected ? Colors.white : Colors.grey.shade400, fontSize: 15)),
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

  // ─── Step 2: Feedback (dynamic based on reason) ───

  String _feedbackTitle() => switch (_selectedReason) {
        'too_expensive' => context.l10n.feedbackTitleTooExpensive,
        'missing_features' => context.l10n.feedbackTitleMissingFeatures,
        'audio_quality' => context.l10n.feedbackTitleAudioQuality,
        'battery_drain' => context.l10n.feedbackTitleBatteryDrain,
        'found_alternative' => context.l10n.feedbackTitleFoundAlternative,
        'not_using_enough' => context.l10n.feedbackTitleNotUsing,
        _ => context.l10n.tellUsMore,
      };

  String _feedbackSubtitle() => switch (_selectedReason) {
        'too_expensive' => context.l10n.feedbackSubtitleTooExpensive,
        'missing_features' => context.l10n.feedbackSubtitleMissingFeatures,
        'audio_quality' => context.l10n.feedbackSubtitleAudioQuality,
        'battery_drain' => context.l10n.feedbackSubtitleBatteryDrain,
        'found_alternative' => context.l10n.feedbackSubtitleFoundAlternative,
        'not_using_enough' => context.l10n.feedbackSubtitleNotUsing,
        _ => context.l10n.cancelReasonDetailHint,
      };

  Widget _stepFeedback() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_feedbackTitle(),
                  style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(_feedbackSubtitle(), style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: TextField(
            controller: _detailsController,
            maxLines: 5,
            maxLength: 300,
            style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.5),
            decoration: InputDecoration(
              filled: true,
              fillColor: Colors.grey.shade900.withValues(alpha: 0.5),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: Colors.grey.shade800)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: Colors.grey.shade800)),
              focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: Colors.grey.shade600)),
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
                    child: Text(context.l10n.continueButton,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
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

  // ─── Step 3: Confirm ───

  Widget _stepConfirm() {
    final provider = context.read<UsageProvider>();
    final sub = provider.subscription?.subscription;
    String renewalDate = '';
    if (sub?.currentPeriodEnd != null) {
      final date = DateTime.fromMillisecondsSinceEpoch(sub!.currentPeriodEnd! * 1000);
      renewalDate = DateFormat.yMMMd().format(date);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.l10n.justAMoment,
                  style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(context.l10n.cancelConsequencesSubtitle,
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // Billing info — prominent at top
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.orange.shade900.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.orange.shade800.withValues(alpha: 0.3)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: FaIcon(FontAwesomeIcons.circleInfo, size: 14, color: Colors.orange.shade400),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    context.l10n.cancelBillingPeriodInfo(renewalDate),
                    style: TextStyle(color: Colors.orange.shade300, fontSize: 13, height: 1.5),
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
              _featureRow(FontAwesomeIcons.infinity, context.l10n.cancelConsequenceNoAccess),
              _featureRow(FontAwesomeIcons.bolt, context.l10n.cancelConsequenceBattery),
              _featureRow(FontAwesomeIcons.solidComments, context.l10n.cancelConsequenceQuality),
              _featureRow(FontAwesomeIcons.gaugeHigh, context.l10n.cancelConsequenceDelay),
              _featureRow(FontAwesomeIcons.userGroup, context.l10n.cancelConsequenceSpeakers),
              _featureRow(FontAwesomeIcons.phone, context.l10n.cancelConsequencePhoneCalls),
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
            child: Column(
              children: [
                // Keep my plan — primary
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: _isCancelling
                        ? null
                        : () {
                            MixpanelManager().subscriptionCancelKeptPlan(step: 3, reason: _selectedReason);
                            Navigator.of(context).pop(false);
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      elevation: 0,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    child: Text(context.l10n.keepMyPlan,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  ),
                ),
                const SizedBox(height: 8),
                // Confirm cancel — de-emphasized
                GestureDetector(
                  onTap: _isCancelling ? null : _confirmCancel,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    child: _isCancelling
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.grey),
                          )
                        : Text(context.l10n.confirmAndCancel,
                            style: TextStyle(color: Colors.grey.shade600, fontSize: 15)),
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
                  color: Colors.grey.shade800.withValues(alpha: 0.5), borderRadius: BorderRadius.circular(10)),
              child: Center(child: FaIcon(icon, size: 14, color: Colors.grey.shade500)),
            ),
            const SizedBox(width: 14),
            Expanded(child: Text(text, style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.3))),
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
