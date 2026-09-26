import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum _VerifyStatus { calling, inProgress, missedCall, verified, timedOut }

class PhoneSetupVerifyPage extends StatefulWidget {
  final String phoneNumber;
  final String? validationCode;

  const PhoneSetupVerifyPage({super.key, required this.phoneNumber, this.validationCode});

  @override
  State<PhoneSetupVerifyPage> createState() => _PhoneSetupVerifyPageState();
}

class _PhoneSetupVerifyPageState extends State<PhoneSetupVerifyPage> with SingleTickerProviderStateMixin {
  _VerifyStatus _status = _VerifyStatus.calling;
  Timer? _pollingTimer;
  int _pollCount = 0;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))
      ..repeat(reverse: true);
    _pulseAnimation = Tween<double>(
      begin: 0.6,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut));
    _startPolling();
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    _pulseController.dispose();
    super.dispose();
  }

  void _startPolling() {
    _pollCount = 0;
    setState(() => _status = _VerifyStatus.calling);

    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      _pollCount++;

      if (_pollCount == 2 && mounted && _status == _VerifyStatus.calling) {
        setState(() => _status = _VerifyStatus.inProgress);
      }

      if (_pollCount == 15 && mounted && _status == _VerifyStatus.inProgress) {
        setState(() => _status = _VerifyStatus.missedCall);
      }

      if (_pollCount > 30) {
        timer.cancel();
        if (!mounted) return;
        setState(() => _status = _VerifyStatus.timedOut);
        return;
      }

      var provider = context.read<PhoneCallProvider>();
      var verified = await provider.checkVerification(widget.phoneNumber);

      if (!mounted) return;

      if (verified) {
        timer.cancel();
        setState(() => _status = _VerifyStatus.verified);
        OmiHaptics.success();
        await Future.delayed(const Duration(milliseconds: 800));
        if (!mounted) return;
        Navigator.of(
          context,
        ).pushAndRemoveUntil(omiPageRoute(builder: (_) => const PhoneCallsPage()), (route) => route.isFirst);
      }
    });
  }

  Future<void> _retry() async {
    setState(() {
      _status = _VerifyStatus.calling;
    });

    var provider = context.read<PhoneCallProvider>();
    var success = await provider.startVerification(widget.phoneNumber);

    if (!mounted) return;

    if (success) {
      _startPolling();
    } else {
      setState(() => _status = _VerifyStatus.timedOut);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
          child: Column(
            children: [
              const SizedBox(height: OmiSpacing.xxl),
              Semantics(
                header: true,
                child: Text(context.l10n.verifyYourNumber, style: OmiType.title2, textAlign: TextAlign.center),
              ),
              const SizedBox(height: OmiSpacing.sm),
              _buildStatusChip(),
              const SizedBox(height: OmiSpacing.xxl),
              _buildStepCard(
                icon: Icons.phone_callback_outlined,
                label: context.l10n.answerTheCallFrom,
                value: '+1 (415) 723-4000',
              ),
              const SizedBox(height: OmiSpacing.md),
              _buildCodeCard(),
              const SizedBox(height: OmiSpacing.xxl),
              Text(
                widget.phoneNumber,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const Spacer(),
              if (_status == _VerifyStatus.missedCall || _status == _VerifyStatus.timedOut) ...[
                OmiButton(
                  label: context.l10n.phoneTryAgain,
                  expand: true,
                  onPressed: () {
                    OmiHaptics.medium();
                    _retry();
                  },
                ),
                const SizedBox(height: OmiSpacing.xxl),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusChip() {
    Color bgColor;
    Widget content;

    Widget pulsingRow(String label) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: _pulseAnimation,
              builder: (_, __) => Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: OmiColors.textPrimary.withValues(alpha: _pulseAnimation.value),
                ),
              ),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Text(label, style: OmiType.footnote),
          ],
        );

    Widget iconRow(IconData icon, String label, Color color) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 16),
            const SizedBox(width: 6),
            Text(label, style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w500)),
          ],
        );

    switch (_status) {
      case _VerifyStatus.calling:
        bgColor = OmiColors.surface1;
        content = pulsingRow(context.l10n.statusCalling);
      case _VerifyStatus.inProgress:
        bgColor = OmiColors.surface1;
        content = pulsingRow(context.l10n.statusCallInProgress);
      case _VerifyStatus.verified:
        bgColor = OmiColors.successSurface;
        content = iconRow(Icons.check, context.l10n.statusVerifiedLabel, OmiColors.success);
      case _VerifyStatus.missedCall:
        bgColor = OmiColors.surface1;
        content = iconRow(Icons.phone_missed, context.l10n.statusCallMissed, OmiColors.warning);
      case _VerifyStatus.timedOut:
        bgColor = OmiColors.dangerSurface;
        content = iconRow(Icons.error_outline, context.l10n.statusTimedOut, OmiColors.danger);
    }

    return Semantics(
      liveRegion: true,
      child: AnimatedContainer(
        duration: OmiMotion.of(context).standard,
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
        decoration: BoxDecoration(color: bgColor, borderRadius: OmiRadius.lgAll),
        child: content,
      ),
    );
  }

  Widget _buildStepCard({required IconData icon, required String label, required String value}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Row(
        children: [
          ExcludeSemantics(child: Icon(icon, color: OmiColors.textPrimary, size: 22)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                const SizedBox(height: OmiSpacing.xxs),
                Text(value, style: OmiType.callout.copyWith(fontWeight: FontWeight.bold)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCodeCard() {
    var code = widget.validationCode;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Row(
        children: [
          const ExcludeSemantics(child: Icon(Icons.dialpad, color: OmiColors.textPrimary, size: 22)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.onTheCallEnterThisCode,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                ),
                const SizedBox(height: OmiSpacing.xs),
                if (code != null && code.isNotEmpty)
                  Text(
                    code.split('').join(' '),
                    style: OmiType.largeTitle.copyWith(fontWeight: FontWeight.bold, letterSpacing: 6),
                  )
                else
                  Text(context.l10n.followTheVoiceInstructions, style: OmiType.callout),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
