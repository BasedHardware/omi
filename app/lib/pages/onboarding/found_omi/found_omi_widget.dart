import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class _SourceOption {
  final String label;

  const _SourceOption(this.label);
}

class FoundOmiWidget extends StatefulWidget {
  final Function goNext;

  const FoundOmiWidget({super.key, required this.goNext});

  @override
  State<FoundOmiWidget> createState() => _FoundOmiWidgetState();
}

class _FoundOmiWidgetState extends State<FoundOmiWidget> {
  String? _selectedSource;
  final TextEditingController _otherController = TextEditingController();

  List<_SourceOption> _getSources(BuildContext context) {
    return [
      _SourceOption(context.l10n.tiktok),
      _SourceOption(context.l10n.youtube),
      _SourceOption(context.l10n.instagram),
      _SourceOption(context.l10n.xTwitter),
      _SourceOption(context.l10n.reddit),
      _SourceOption(context.l10n.linkedIn),
      _SourceOption(context.l10n.friendWordOfMouth),
      _SourceOption(context.l10n.coworker),
      _SourceOption(context.l10n.event),
      _SourceOption(context.l10n.appStore),
      _SourceOption(context.l10n.googleSearch),
      _SourceOption(context.l10n.otherSource),
    ];
  }

  bool get _canContinue {
    if (_selectedSource == null) return false;
    if (_selectedSource == context.l10n.otherSource) {
      return _otherController.text.trim().isNotEmpty;
    }
    return true;
  }

  @override
  void dispose() {
    _otherController.dispose();
    super.dispose();
  }

  void _submit() {
    FocusManager.instance.primaryFocus?.unfocus();
    final source = _selectedSource == context.l10n.otherSource ? _otherController.text.trim() : _selectedSource!;
    SharedPreferencesUtil().foundOmiSource = source;
    updateUserOnboardingState(acquisitionSource: source);
    PlatformManager.instance.analytics.onboardingUserAcquisitionSource(source);
    OmiHaptics.selection();
    widget.goNext();
  }

  /// The survey is optional: Skip moves on without recording a source.
  void _skip() {
    FocusManager.instance.primaryFocus?.unfocus();
    OmiHaptics.selection();
    widget.goNext();
  }

  @override
  Widget build(BuildContext context) {
    final sources = _getSources(context);
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          OnboardingHeader(title: context.l10n.howDidYouHearAboutOmi, subtitle: context.l10n.foundOmiOptionalHint),
          const SizedBox(height: OmiSpacing.lg),
          // v2 Source: the answers as wrapped chips; one can be chosen.
          Wrap(
            spacing: OmiSpacing.xs,
            children: [
              for (final source in sources)
                OmiChip(
                  large: true,
                  label: source.label,
                  selected: _selectedSource == source.label,
                  onTap: () => setState(() {
                    _selectedSource = _selectedSource == source.label ? null : source.label;
                    if (_selectedSource != context.l10n.otherSource) {
                      _otherController.clear();
                    }
                  }),
                ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xs),
          if (_selectedSource == context.l10n.otherSource) ...[
            const SizedBox(height: OmiSpacing.xxs),
            Container(
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
              child: TextField(
                controller: _otherController,
                style: OmiType.callout,
                decoration: InputDecoration(
                  hintText: context.l10n.pleaseSpecify,
                  hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: OmiSpacing.md),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ],
        footer: [
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
            key: const Key('found_omi_continue'),
            label: context.l10n.continueButton,
            expand: true,
            onPressed: _canContinue ? _submit : null,
          ),
          OmiButton.tertiary(
            key: const Key('found_omi_skip'),
            label: context.l10n.skip,
            expand: true,
            onPressed: _skip,
          ),
        ],
      ),
    );
  }
}
