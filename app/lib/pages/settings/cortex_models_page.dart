import 'package:flutter/material.dart';
import 'package:omi/services/cortex/model_config.dart';
import 'package:omi/services/cortex/providers.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Cortex → Settings → Models. Pick the AI engine: the built-in backend, or a
/// local/cloud provider (grouped by region) with your own API key.
class CortexModelsPage extends StatefulWidget {
  const CortexModelsPage({super.key});

  @override
  State<CortexModelsPage> createState() => _CortexModelsPageState();
}

class _CortexModelsPageState extends State<CortexModelsPage> {
  final _cfg = CortexModelConfig.instance;

  static const _bg = Color(0xFF000000);
  static const _card = Color(0xFF1C1C1E);

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final provider = cortexProviderById(_cfg.providerId);
    final usingProvider = _cfg.mode == CortexEngineMode.provider;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg,
        title: Text(l.cortexModelsTitle),
        leading: IconButton(icon: const Icon(Icons.arrow_back_ios_new, size: 18), onPressed: () => Navigator.pop(context)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _section([
            _rowLabel(Icons.memory, l.cortexEngineTitle, l.cortexEngineSubtitle),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: DropdownButtonFormField<CortexEngineMode>(
                value: _cfg.mode,
                dropdownColor: _card,
                decoration: const InputDecoration(border: OutlineInputBorder()),
                items: [
                  DropdownMenuItem(value: CortexEngineMode.backend, child: Text(l.cortexEngineBuiltin)),
                  DropdownMenuItem(value: CortexEngineMode.provider, child: Text(l.cortexEngineProvider)),
                ],
                onChanged: (v) => setState(() => _cfg.mode = v ?? CortexEngineMode.backend),
              ),
            ),
          ]),
          if (usingProvider) ...[
            const SizedBox(height: 16),
            _section([
              _rowLabel(Icons.cloud_outlined, l.cortexProviderTitle, l.cortexProviderSubtitle),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: DropdownButtonFormField<String>(
                  value: _cfg.providerId,
                  dropdownColor: _card,
                  isExpanded: true,
                  hint: Text(l.cortexChooseProvider),
                  decoration: const InputDecoration(border: OutlineInputBorder()),
                  items: [
                    // Mobile is cloud-only: phones can't run real (vision) local models.
                    for (final g in cortexProvidersByRegion(cloudOnly: kCortexMobileCloudOnly)) ...[
                      // Non-selectable region header. A unique sentinel value keeps
                      // DropdownButton's value assertion happy (no duplicate nulls).
                      DropdownMenuItem<String>(
                        value: '__region_${g.region.name}',
                        enabled: false,
                        child: Text(g.label, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                      ),
                      ...g.providers.map((p) => DropdownMenuItem<String>(value: p.id, child: Text(p.name))),
                    ],
                  ],
                  onChanged: (v) => setState(() {
                    _cfg.providerId = v;
                    _cfg.modelId = null;
                  }),
                ),
              ),
            ]),
            if (provider != null) ...[
              const SizedBox(height: 16),
              _section([
                _rowLabel(Icons.auto_awesome, l.cortexModelLabel, provider.note ?? ''),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  child: DropdownButtonFormField<String>(
                    value: provider.models.any((m) => m.id == _cfg.modelId) ? _cfg.modelId : null,
                    dropdownColor: _card,
                    isExpanded: true,
                    hint: Text(l.cortexChooseModel),
                    decoration: const InputDecoration(border: OutlineInputBorder()),
                    items: provider.models
                        .map((m) => DropdownMenuItem<String>(
                            value: m.id, child: Text(m.note == null ? m.label : '${m.label} — ${m.note}')))
                        .toList(),
                    onChanged: (v) => setState(() => _cfg.modelId = v),
                  ),
                ),
                if (provider.dynamicModels)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: TextFormField(
                      initialValue: _cfg.modelId ?? '',
                      decoration: InputDecoration(border: const OutlineInputBorder(), hintText: l.cortexModelIdHint),
                      onChanged: (v) => _cfg.modelId = v.trim().isEmpty ? null : v.trim(),
                    ),
                  ),
              ]),
              if (provider.id == 'custom') ...[
                const SizedBox(height: 16),
                _section([
                  _rowLabel(Icons.link, l.cortexBaseUrl, ''),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: TextFormField(
                      initialValue: _cfg.customBaseUrl ?? '',
                      decoration: const InputDecoration(border: OutlineInputBorder(), hintText: 'https://your-endpoint/v1'),
                      onChanged: (v) => _cfg.customBaseUrl = v.trim().isEmpty ? null : v.trim(),
                    ),
                  ),
                ]),
              ],
              if (provider.requiresApiKey) ...[
                const SizedBox(height: 16),
                _section([
                  _rowLabel(Icons.key, l.cortexApiKey, l.cortexApiKeyHint),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: TextFormField(
                      initialValue: _cfg.apiKey(provider.id),
                      obscureText: true,
                      decoration: const InputDecoration(border: OutlineInputBorder()),
                      onChanged: (v) => _cfg.setApiKey(provider.id, v.trim()),
                    ),
                  ),
                ]),
              ],
            ],
          ],
        ],
      ),
    );
  }

  Widget _section(List<Widget> children) => Container(
        decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      );

  Widget _rowLabel(IconData icon, String title, String subtitle) => Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, color: Colors.grey.shade400, size: 18),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(subtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                  ],
                ],
              ),
            ),
          ],
        ),
      );
}
