import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

class _SourceOption {
  final String label;
  final IconData icon;

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

  @override
  Widget build(BuildContext context) {
    final sources = _getSources(context);

    return Column(
      children: [
        // Background area - takes remaining space for background image
        Expanded(
          child: Container(),
        ),

        // Bottom drawer card
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(32, 20, 32, 0),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(40),
              topRight: Radius.circular(40),
            ),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 10),
                Text(
                  context.l10n.whereDidYouHearAboutOmi,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                SizedBox(
                  height: 250,
                  child: ListView.separated(
                    padding: EdgeInsets.zero,
                    itemCount: sources.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      final source = sources[index];
                      final isSelected = _selectedSource == source.label;
                      return GestureDetector(
                        onTap: () {
                          setState(() {
                            _selectedSource = isSelected ? null : source.label;
                            if (_selectedSource != context.l10n.otherSource) {
                              _otherController.clear();
                            }
                          });
                        },
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                          decoration: BoxDecoration(
                            color: isSelected ? Colors.white : Colors.grey[900],
                            borderRadius: BorderRadius.circular(40),
                            border: Border.all(
                              color: isSelected ? Colors.white : Colors.grey[700]!,
                              width: 1,
                            ),
                          ),
                          child: Row(
                            children: [
                              FaIcon(
                                source.icon,
                                size: 18,
                                color: isSelected ? Colors.black : Colors.white,
                              ),
                              const SizedBox(width: 14),
                              Text(
                                source.label,
                                style: TextStyle(
                                  color: isSelected ? Colors.black : Colors.white,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500,
                                  fontFamily: 'Manrope',
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                if (_selectedSource == context.l10n.otherSource) ...[
                  const SizedBox(height: 12),
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.grey[900],
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey[700]!, width: 1),
                    ),
                    child: TextField(
                      controller: _otherController,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontFamily: 'Manrope',
                      ),
                      textAlign: TextAlign.center,
                      decoration: InputDecoration(
                        hintText: context.l10n.pleaseSpecify,
                        hintStyle: TextStyle(
                          color: Colors.grey[500],
                          fontSize: 16,
                          fontFamily: 'Manrope',
                        ),
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _canContinue
                        ? () {
                            FocusManager.instance.primaryFocus?.unfocus();
                            final source = _selectedSource == context.l10n.otherSource
                                ? _otherController.text.trim()
                                : _selectedSource!;
                            SharedPreferencesUtil().foundOmiSource = source;
                            updateUserOnboardingState(acquisitionSource: source);
                            MixpanelManager().onboardingUserAcquisitionSource(source);
                            widget.goNext();
                          }
                        : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: _canContinue ? Colors.white : Colors.grey[800],
                      foregroundColor: _canContinue ? Colors.black : Colors.grey[600],
                      disabledBackgroundColor: Colors.grey[800],
                      disabledForegroundColor: Colors.grey[600],
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.continueButton,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        fontFamily: 'Manrope',
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
