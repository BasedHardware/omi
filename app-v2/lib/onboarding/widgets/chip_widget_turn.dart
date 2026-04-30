import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class _ChipOption {
  final String id;
  final String label;
  const _ChipOption(this.id, this.label);
}

class LanguageChipsTurn extends StatelessWidget {
  final String turnId;
  const LanguageChipsTurn({super.key, required this.turnId});

  static const List<_ChipOption> _languages = [
    _ChipOption('en', 'English'),
    _ChipOption('pt-BR', 'Português (Brasil)'),
  ];

  @override
  Widget build(BuildContext context) {
    final provider = context.read<OnboardingChatProvider>();
    return _ChipWrap(
      options: _languages,
      onTap: (opt) => provider.reportWidgetCapture(context, turnId, opt.id),
    );
  }
}

/// Public lookup for chat-replay code that needs to render the human label
/// for a saved language id without re-touching the chip widget.
const Map<String, String> kLanguageLabelById = {
  'en': 'English',
  'pt-BR': 'Português (Brasil)',
};

class _ChipWrap extends StatelessWidget {
  final List<_ChipOption> options;
  final void Function(_ChipOption) onTap;
  const _ChipWrap({required this.options, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: options
            .map((o) => InkWell(
                  borderRadius: BorderRadius.circular(AppStyles.radiusPill),
                  onTap: () => onTap(o),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.backgroundSecondary,
                      borderRadius: BorderRadius.circular(AppStyles.radiusPill),
                      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                    ),
                    child: Text(
                      o.label,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textPrimary),
                    ),
                  ),
                ))
            .toList(),
      ),
    );
  }
}

// Used in unit tests / future steps where a generic chip turn is needed.
class GenericChipsTurn extends StatelessWidget {
  final String turnId;
  final List<({String id, String label})> options;
  const GenericChipsTurn({super.key, required this.turnId, required this.options});

  @override
  Widget build(BuildContext context) {
    final provider = context.read<OnboardingChatProvider>();
    final mapped = options.map((o) => _ChipOption(o.id, o.label)).toList();
    return _ChipWrap(
      options: mapped,
      onTap: (opt) => provider.reportWidgetCapture(context, turnId, opt.label),
    );
  }
}

