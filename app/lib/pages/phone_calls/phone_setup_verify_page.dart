import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/phone_call_provider.dart';

enum _VerifyStatus { calling, inProgress, verified, timedOut }

class PhoneSetupVerifyPage extends StatefulWidget {
  final String phoneNumber;
  final String? validationCode;

  const PhoneSetupVerifyPage({
    super.key,
    required this.phoneNumber,
    this.validationCode,
  });

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
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
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

      // After first poll, update to "in progress"
      if (_pollCount == 2 && mounted && _status == _VerifyStatus.calling) {
        setState(() => _status = _VerifyStatus.inProgress);
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
        HapticFeedback.mediumImpact();
        await Future.delayed(const Duration(milliseconds: 800));
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const PhoneCallsPage()),
          (route) => route.isFirst,
        );
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
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              const SizedBox(height: 32),
              const Text(
                'Verify your number',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              _buildStatusChip(),
              const SizedBox(height: 32),
              // Step cards
              _buildStepCard(
                icon: Icons.phone_callback_outlined,
                label: 'Answer the call from',
                value: '+1 (415) 723-4000',
              ),
              const SizedBox(height: 16),
              _buildCodeCard(),
              const SizedBox(height: 32),
              // User's phone number
              Text(
                widget.phoneNumber,
                style: TextStyle(fontSize: 16, color: Colors.grey[500]),
                textAlign: TextAlign.center,
              ),
              const Spacer(),
              // Retry button (only when timed out)
              if (_status == _VerifyStatus.timedOut) ...[
                GestureDetector(
                  onTap: () {
                    HapticFeedback.mediumImpact();
                    _retry();
                  },
                  child: Container(
                    width: double.infinity,
                    height: 56,
                    decoration: BoxDecoration(
                      color: Colors.deepPurple,
                      borderRadius: BorderRadius.circular(28),
                    ),
                    alignment: Alignment.center,
                    child: const Text(
                      'Try Again',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
                    ),
                  ),
                ),
                const SizedBox(height: 32),
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

    switch (_status) {
      case _VerifyStatus.calling:
        bgColor = const Color(0xFF1F1F25);
        content = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: _pulseAnimation,
              builder: (_, __) => Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: _pulseAnimation.value),
                ),
              ),
            ),
            const SizedBox(width: 8),
            const Text('Calling...', style: TextStyle(fontSize: 13, color: Colors.white)),
          ],
        );
      case _VerifyStatus.inProgress:
        bgColor = const Color(0xFF1F1F25);
        content = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: _pulseAnimation,
              builder: (_, __) => Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: _pulseAnimation.value),
                ),
              ),
            ),
            const SizedBox(width: 8),
            const Text('Call in progress', style: TextStyle(fontSize: 13, color: Colors.white)),
          ],
        );
      case _VerifyStatus.verified:
        bgColor = Colors.green[700]!;
        content = const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check, color: Colors.white, size: 16),
            SizedBox(width: 6),
            Text('Verified', style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.w500)),
          ],
        );
      case _VerifyStatus.timedOut:
        bgColor = Colors.red.shade900;
        content = const Text('Timed out', style: TextStyle(fontSize: 13, color: Colors.white));
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(16),
      ),
      child: content,
    );
  }

  Widget _buildStepCard({required IconData icon, required String label, required String value}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Icon(icon, color: Colors.white, size: 22),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: TextStyle(fontSize: 14, color: Colors.grey[400])),
                const SizedBox(height: 4),
                Text(
                  value,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                ),
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
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.dialpad, color: Colors.white, size: 22),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('On the call, enter this code', style: TextStyle(fontSize: 14, color: Colors.grey[400])),
                const SizedBox(height: 8),
                if (code != null && code.isNotEmpty)
                  Text(
                    code.split('').join(' '),
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                      letterSpacing: 6,
                    ),
                  )
                else
                  const Text(
                    'Follow the voice instructions',
                    style: TextStyle(fontSize: 16, color: Colors.white),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
