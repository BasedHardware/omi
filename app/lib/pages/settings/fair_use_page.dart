import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/utils/l10n_extensions.dart';

class FairUsePage extends StatefulWidget {
  const FairUsePage({super.key});

  @override
  State<FairUsePage> createState() => _FairUsePageState();
}

class _FairUsePageState extends State<FairUsePage> {
  Map<String, dynamic>? _status;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final result = await getFairUseStatus();
      if (mounted) {
        setState(() {
          _status = result;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        title: Text(context.l10n.fairUsePolicy),
        leading: IconButton(icon: const Icon(Icons.arrow_back_ios), onPressed: () => Navigator.of(context).pop()),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : _error != null
              ? _buildError()
              : _status == null
                  ? _buildUnavailable()
                  : RefreshIndicator(
                      onRefresh: _loadStatus,
                      child: SingleChildScrollView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildStageCard(),
                            const SizedBox(height: 16),
                            _buildUsageSection(),
                            const SizedBox(height: 16),
                            _buildMessageCard(),
                            const SizedBox(height: 16),
                            _buildInfoSection(),
                          ],
                        ),
                      ),
                    ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.red, size: 40),
            const SizedBox(height: 16),
            Text(
              context.l10n.fairUseLoadError,
              style: const TextStyle(color: Colors.white, fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            TextButton(
              onPressed: _loadStatus,
              child: Text(context.l10n.retry, style: const TextStyle(color: Color(0xFF8B5CF6))),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUnavailable() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const FaIcon(FontAwesomeIcons.solidCircleCheck, color: Color(0xFF34D399), size: 40),
            const SizedBox(height: 16),
            Text(
              context.l10n.fairUseStatusNormal,
              style: const TextStyle(color: Colors.white, fontSize: 16),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStageCard() {
    final stage = _status!['stage'] as String? ?? 'none';
    final caseRef = _status!['case_ref'] as String? ?? '';

    Color stageColor;
    IconData stageIcon;
    String stageLabel;

    switch (stage) {
      case 'warning':
        stageColor = const Color(0xFFFBBF24);
        stageIcon = FontAwesomeIcons.triangleExclamation;
        stageLabel = context.l10n.fairUseStageWarning;
        break;
      case 'throttle':
        stageColor = const Color(0xFFF97316);
        stageIcon = FontAwesomeIcons.gaugeHigh;
        stageLabel = context.l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        stageColor = const Color(0xFFEF4444);
        stageIcon = FontAwesomeIcons.ban;
        stageLabel = context.l10n.fairUseStageRestrict;
        break;
      default:
        stageColor = const Color(0xFF34D399);
        stageIcon = FontAwesomeIcons.solidCircleCheck;
        stageLabel = context.l10n.fairUseStageNormal;
    }

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: stageColor.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          FaIcon(stageIcon, color: stageColor, size: 32),
          const SizedBox(height: 12),
          Text(
            stageLabel,
            style: TextStyle(color: stageColor, fontSize: 18, fontWeight: FontWeight.w600),
          ),
          if (caseRef.isNotEmpty) ...[
            const SizedBox(height: 8),
            GestureDetector(
              onTap: () {
                Clipboard.setData(ClipboardData(text: caseRef));
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('$caseRef copied'),
                    duration: const Duration(seconds: 2),
                    backgroundColor: const Color(0xFF2C2C2E),
                  ),
                );
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(8)),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      caseRef,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontFamily: 'monospace'),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.copy, size: 14, color: Color(0xFF8E8E93)),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildUsageSection() {
    final usagePct = _status!['usage_pct'] as Map<String, dynamic>? ?? {};
    final limits = _status!['limits'] as Map<String, dynamic>? ?? {};
    final speechToday = (_status!['speech_hours_today'] as num?)?.toDouble() ?? 0;
    final speech3day = (_status!['speech_hours_3day'] as num?)?.toDouble() ?? 0;
    final speechWeekly = (_status!['speech_hours_weekly'] as num?)?.toDouble() ?? 0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.fairUseSpeechUsage,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          _buildUsageBar(
            label: context.l10n.fairUseToday,
            hours: speechToday,
            limit: (limits['daily_hours'] as num?)?.toDouble() ?? 2.0,
            pct: (usagePct['daily'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 12),
          _buildUsageBar(
            label: context.l10n.fairUse3Day,
            hours: speech3day,
            limit: (limits['three_day_hours'] as num?)?.toDouble() ?? 8.0,
            pct: (usagePct['three_day'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 12),
          _buildUsageBar(
            label: context.l10n.fairUseWeekly,
            hours: speechWeekly,
            limit: (limits['weekly_hours'] as num?)?.toDouble() ?? 10.0,
            pct: (usagePct['weekly'] as num?)?.toDouble() ?? 0,
          ),
        ],
      ),
    );
  }

  Widget _buildUsageBar({required String label, required double hours, required double limit, required double pct}) {
    Color barColor;
    if (pct >= 100) {
      barColor = const Color(0xFFEF4444);
    } else if (pct >= 80) {
      barColor = const Color(0xFFFBBF24);
    } else {
      barColor = const Color(0xFF8B5CF6);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13)),
            Text(
              '${hours.toStringAsFixed(1)}h / ${limit.toStringAsFixed(0)}h',
              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: (pct / 100).clamp(0.0, 1.0),
            backgroundColor: const Color(0xFF2C2C2E),
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
            minHeight: 6,
          ),
        ),
      ],
    );
  }

  Widget _buildMessageCard() {
    final message = _status!['message'] as String? ?? '';
    if (message.isEmpty) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FaIcon(FontAwesomeIcons.circleInfo, color: Color(0xFF8E8E93), size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(message, style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 14, height: 1.4)),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoSection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.fairUseAboutTitle,
            style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.fairUseAboutBody,
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, height: 1.5),
          ),
        ],
      ),
    );
  }
}
