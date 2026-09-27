import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class _SourceOption {
  final String label;
  final FaIconData icon;

  const _SourceOption(this.label, this.icon);
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
      _SourceOption(context.l10n.tiktok, FontAwesomeIcons.tiktok),
      _SourceOption(context.l10n.youtube, FontAwesomeIcons.youtube),
      _SourceOption(context.l10n.instagram, FontAwesomeIcons.instagram),
      _SourceOption(context.l10n.xTwitter, FontAwesomeIcons.xTwitter),
      _SourceOption(context.l10n.reddit, FontAwesomeIcons.reddit),
      _SourceOption(context.l10n.linkedIn, FontAwesomeIcons.linkedin),
      _SourceOption(context.l10n.friendWordOfMouth, FontAwesomeIcons.userGroup),
      _SourceOption(context.l10n.coworker, FontAwesomeIcons.briefcase),
      _SourceOption(context.l10n.event, FontAwesomeIcons.calendarDay),
      _SourceOption(context.l10n.appStore, FontAwesomeIcons.appStore),
      _SourceOption(context.l10n.googleSearch, FontAwesomeIcons.google),
      _SourceOption(context.l10n.otherSource, FontAwesomeIcons.ellipsis),
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
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xxl, OmiSpacing.xl, OmiSpacing.xxl, 0),
        content: [
          Semantics(
            header: true,
            child: Text(context.l10n.whereDidYouHearAboutOmi, style: OmiType.title1, textAlign: TextAlign.center),
          ),
          const SizedBox(height: OmiSpacing.xl),
          for (final source in sources) ...[
            _SourceTile(
              option: source,
              selected: _selectedSource == source.label,
              onTap: () {
                OmiHaptics.light();
                setState(() {
                  _selectedSource = _selectedSource == source.label ? null : source.label;
                  if (_selectedSource != context.l10n.otherSource) {
                    _otherController.clear();
                  }
                });
              },
            ),
            const SizedBox(height: 10),
          ],
          if (_selectedSource == context.l10n.otherSource) ...[
            const SizedBox(height: OmiSpacing.xxs),
            Container(
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                borderRadius: OmiRadius.lgAll,
                border: Border.all(color: OmiColors.border),
              ),
              child: TextField(
                controller: _otherController,
                style: OmiType.callout,
                textAlign: TextAlign.center,
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

class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.option, required this.selected, required this.onTap});

  final _SourceOption option;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? OmiColors.accent : OmiColors.surface1,
        shape: RoundedRectangleBorder(
          borderRadius: OmiRadius.pillAll,
          side: BorderSide(color: selected ? OmiColors.accent : OmiColors.border),
        ),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 48),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  ExcludeSemantics(child: FaIcon(option.icon, size: 18, color: foreground)),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      option.label,
                      style: OmiType.subhead.copyWith(color: foreground, fontWeight: FontWeight.w500),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
