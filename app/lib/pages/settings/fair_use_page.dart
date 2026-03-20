import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
        if (result == null) {
          setState(() {
            _error = 'Unable to load fair use status';
            _isLoading = false;
          });
        } else {
          setState(() {
            _status = result;
            _isLoading = false;
          });
        }
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
                  ? _buildError()
                  : RefreshIndicator(
                      onRefresh: _loadStatus,
                      child: SingleChildScrollView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildStatusBanner(),
                            _buildUsageSection(),
                            _buildBudgetSection(),
                            _buildMessageBanner(),
                            const SizedBox(height: 24),
                            _buildAboutFooter(),
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
            Text(
              context.l10n.fairUseLoadError,
              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
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

  Widget _buildStatusBanner() {
    final stage = _status!['stage'] as String? ?? 'none';
    if (stage == 'none') return const SizedBox.shrink();

    final caseRef = _status!['case_ref'] as String? ?? '';

    Color dotColor;
    String stageLabel;

    switch (stage) {
      case 'warning':
        dotColor = const Color(0xFFFBBF24);
        stageLabel = context.l10n.fairUseStageWarning;
        break;
      case 'throttle':
        dotColor = const Color(0xFFF97316);
        stageLabel = context.l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        dotColor = const Color(0xFFEF4444);
        stageLabel = context.l10n.fairUseStageRestrict;
        break;
      default:
        return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: dotColor.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
            ),
            const SizedBox(width: 10),
            Text(
              stageLabel,
              style: TextStyle(color: dotColor, fontSize: 14, fontWeight: FontWeight.w500),
            ),
            const Spacer(),
            if (caseRef.isNotEmpty)
              GestureDetector(
                onTap: () {
                  Clipboard.setData(ClipboardData(text: caseRef));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(context.l10n.fairUseCaseRefCopied(caseRef)),
                      duration: const Duration(seconds: 2),
                      backgroundColor: const Color(0xFF2C2C2E),
                    ),
                  );
                },
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      caseRef,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 12, fontFamily: 'monospace'),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.copy, size: 12, color: Color(0xFF8E8E93)),
                  ],
                ),
              ),
          ],
        ),
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
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 16),
          _buildUsageBar(
            label: context.l10n.fairUseToday,
            hours: speechToday,
            limit: (limits['daily_hours'] as num?)?.toDouble() ?? 2.0,
            pct: (usagePct['daily'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 14),
          _buildUsageBar(
            label: context.l10n.fairUse3Day,
            hours: speech3day,
            limit: (limits['three_day_hours'] as num?)?.toDouble() ?? 8.0,
            pct: (usagePct['three_day'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 14),
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
    final barColor = pct >= 100
        ? const Color(0xFFEF4444)
        : pct >= 80
            ? const Color(0xFFFBBF24)
            : const Color(0xFF8B5CF6);

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
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: (pct / 100).clamp(0.0, 1.0),
            backgroundColor: const Color(0xFF2C2C2E),
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
            minHeight: 4,
          ),
        ),
      ],
    );
  }

  Widget _buildBudgetSection() {
    final stage = _status!['stage'] as String? ?? 'none';
    if (stage != 'restrict') return const SizedBox.shrink();

    final dgBudget = _status!['dg_budget'] as Map<String, dynamic>?;
    if (dgBudget == null) return const SizedBox.shrink();

    final dailyLimitMs = (dgBudget['daily_limit_ms'] as num?)?.toInt() ?? 0;
    final usedMs = (dgBudget['used_ms'] as num?)?.toInt() ?? 0;
    final exhausted = dgBudget['exhausted'] as bool? ?? false;
    final resetsAt = dgBudget['resets_at'] as String? ?? '';

    if (dailyLimitMs <= 0) return const SizedBox.shrink();

    final usedMin = (usedMs / 60000).round();
    final limitMin = (dailyLimitMs / 60000).round();
    final pct = (usedMs / dailyLimitMs * 100).clamp(0.0, 100.0);
    final barColor = exhausted ? const Color(0xFFEF4444) : const Color(0xFF8B5CF6);

    String resetLabel = '';
    if (resetsAt.isNotEmpty) {
      try {
        final resetTime = DateTime.parse(resetsAt);
        final now = DateTime.now().toUtc();
        final diff = resetTime.difference(now);
        if (diff.inHours > 0) {
          resetLabel = context.l10n.fairUseBudgetResetsAt('${diff.inHours}h');
        } else if (diff.inMinutes > 0) {
          resetLabel = context.l10n.fairUseBudgetResetsAt('${diff.inMinutes}m');
        }
      } catch (_) {}
    }

    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: exhausted ? const Color(0xFFEF4444).withValues(alpha: 0.06) : const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  context.l10n.fairUseDailyTranscription,
                  style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500),
                ),
                Text(
                  context.l10n.fairUseBudgetUsed('$usedMin', '$limitMin'),
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: (pct / 100).clamp(0.0, 1.0),
                backgroundColor: const Color(0xFF2C2C2E),
                valueColor: AlwaysStoppedAnimation<Color>(barColor),
                minHeight: 4,
              ),
            ),
            if (exhausted) ...[
              const SizedBox(height: 10),
              Text(
                context.l10n.fairUseBudgetExhausted,
                style: const TextStyle(color: Color(0xFFEF4444), fontSize: 13, fontWeight: FontWeight.w500),
              ),
            ],
            if (resetLabel.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                resetLabel,
                style: const TextStyle(color: Color(0xFF636366), fontSize: 12),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildMessageBanner() {
    final message = _status!['message'] as String? ?? '';
    if (message.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: Color(0xFF8E8E93), size: 16),
            const SizedBox(width: 10),
            Expanded(
              child: Text(message, style: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 13, height: 1.4)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAboutFooter() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.fairUseAboutTitle,
            style: const TextStyle(color: Color(0xFF636366), fontSize: 12, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 4),
          Text(
            context.l10n.fairUseAboutBody,
            style: const TextStyle(color: Color(0xFF48484A), fontSize: 12, height: 1.4),
          ),
        ],
      ),
    );
  }
}
