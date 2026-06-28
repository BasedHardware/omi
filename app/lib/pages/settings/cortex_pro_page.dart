import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/services/cortex/license.dart';
import 'package:omi/services/cortex/model_config.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Cortex → Settings → Cortex Pro. Plan status, start trial, redeem key, Pro
/// feature list, and the Pro-gated cloud-sync toggle.
class CortexProPage extends StatefulWidget {
  const CortexProPage({super.key});

  @override
  State<CortexProPage> createState() => _CortexProPageState();
}

class _CortexProPageState extends State<CortexProPage> {
  final _license = CortexLicense.instance;
  final _sync = CortexCloudSync.instance;
  final _keyController = TextEditingController();
  String _keyError = '';
  String _syncMsg = '';

  static const _bg = Color(0xFF000000);
  static const _card = Color(0xFF1C1C1E);
  static const _accent = Colors.blue;
  static const _waitlist = 'https://cortex.apym.io';

  @override
  void dispose() {
    _keyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final tier = _license.tier;
    final isPro = _license.isProActive;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg,
        title: Text(l.cortexProTitle),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _section([
            ListTile(
              leading: const Icon(Icons.workspace_premium, color: _accent),
              title: Text(_planTitle(l, tier), style: const TextStyle(color: Colors.white)),
              subtitle: Text(_planSub(l, tier), style: TextStyle(color: Colors.grey.shade500)),
              trailing: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  border: Border.all(color: isPro ? _accent : Colors.white24),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(_badge(tier), style: TextStyle(color: isPro ? _accent : Colors.white70, fontSize: 11)),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          if (!isPro && _license.canStartTrial)
            _section([
              ListTile(
                leading: const Icon(Icons.timer_outlined, color: Colors.white70),
                title: Text(l.cortexStartTrial, style: const TextStyle(color: Colors.white)),
                subtitle: Text(l.cortexStartTrialSub, style: TextStyle(color: Colors.grey.shade500)),
                trailing: ElevatedButton(
                  onPressed: () => setState(() => _license.startTrial()),
                  child: Text(l.cortexStartTrialButton),
                ),
              ),
            ]),
          if (!isPro) ...[
            const SizedBox(height: 16),
            _section([
              ListTile(
                leading: const Icon(Icons.rocket_launch_outlined, color: Colors.white70),
                title: Text(l.cortexJoinWaitlist, style: const TextStyle(color: Colors.white)),
                subtitle: Text(l.cortexJoinWaitlistSub, style: TextStyle(color: Colors.grey.shade500)),
                trailing: ElevatedButton(
                  onPressed: () => launchUrl(Uri.parse(_waitlist), mode: LaunchMode.externalApplication),
                  child: Text(l.cortexJoinWaitlistButton),
                ),
              ),
            ]),
          ],
          const SizedBox(height: 16),
          _section([
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text(
                l.cortexRedeemKey,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _keyController,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        hintText: 'CORTEX-PRO-XXXX-XXXX-XXXX',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () => setState(() {
                      if (_license.redeemProKey(_keyController.text)) {
                        _keyController.clear();
                        _keyError = '';
                      } else {
                        _keyError = l.cortexInvalidKey;
                      }
                    }),
                    child: Text(l.cortexRedeemButton),
                  ),
                ],
              ),
            ),
            if (_keyError.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                child: Text(_keyError, style: const TextStyle(color: Colors.amber, fontSize: 13)),
              ),
          ]),
          const SizedBox(height: 16),
          _section([
            for (final f in kProFeatures)
              ListTile(
                leading: Icon(Icons.check_circle, color: isPro ? _accent : Colors.white24, size: 20),
                title: Text(f.label, style: const TextStyle(color: Colors.white, fontSize: 15)),
                subtitle: Text(f.description, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
              ),
          ]),
          const SizedBox(height: 16),
          _section([
            SwitchListTile(
              value: _sync.enabled && isPro,
              activeColor: _accent,
              title: Text(l.cortexCloudSync, style: const TextStyle(color: Colors.white)),
              subtitle: Text(
                isPro ? l.cortexCloudSyncSub : l.cortexProOnly,
                style: TextStyle(color: Colors.grey.shade500),
              ),
              onChanged: isPro ? (v) => setState(() => _sync.enabled = v) : null,
            ),
            if (isPro && _sync.enabled)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: Row(
                  children: [
                    OutlinedButton.icon(
                      icon: const Icon(Icons.sync, size: 16),
                      label: Text(l.cortexSyncNow),
                      onPressed: () async {
                        final r = await _sync.run();
                        if (mounted) setState(() => _syncMsg = r.reason);
                      },
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(_syncMsg, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                    ),
                  ],
                ),
              ),
          ]),
        ],
      ),
    );
  }

  String _planTitle(l, CortexTier tier) => l.cortexPlan;

  String _planSub(l, CortexTier tier) {
    switch (tier) {
      case CortexTier.pro:
        return l.cortexPlanPro;
      case CortexTier.trial:
        return '${l.cortexPlanTrial} — ${_license.trialDaysRemaining()} ${l.cortexDaysRemaining}';
      case CortexTier.free:
        return l.cortexPlanFree;
    }
  }

  String _badge(CortexTier tier) {
    switch (tier) {
      case CortexTier.pro:
        return 'PRO';
      case CortexTier.trial:
        return 'TRIAL';
      case CortexTier.free:
        return 'FREE';
    }
  }

  Widget _section(List<Widget> children) => Container(
    decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
  );
}
