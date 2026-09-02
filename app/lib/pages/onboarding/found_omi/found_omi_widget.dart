import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
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
  final FocusNode _otherFocusNode = FocusNode();

  // 12 sources fill a 4×3 capsule grid. "Other" is the last cell; tapping
  // it keeps the chip selected and opens a text field under the grid.
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

  bool get _isOtherSelected => _selectedSource == context.l10n.otherSource;

  bool get _canContinue {
    if (_selectedSource == null) return false;
    if (_isOtherSelected) return _otherController.text.trim().isNotEmpty;
    return true;
  }

  void _selectFixed(String label) {
    setState(() {
      _selectedSource = _selectedSource == label ? null : label;
      _otherController.clear();
    });
  }

  void _selectOther() {
    setState(() => _selectedSource = context.l10n.otherSource);
    WidgetsBinding.instance.addPostFrameCallback((_) => _otherFocusNode.requestFocus());
  }

  void _deselectOther() {
    _otherFocusNode.unfocus();
    setState(() {
      _selectedSource = null;
      _otherController.clear();
    });
  }

  @override
  void dispose() {
    _otherController.dispose();
    _otherFocusNode.dispose();
    super.dispose();
  }

  Widget _sourceGrid(BuildContext context) {
    final options = _getSources(context);
    const columns = 4;
    const gap = 8.0;
    final otherLabel = context.l10n.otherSource;

    return Column(
      children: [
        for (var row = 0; row < 3; row++) ...[
          if (row > 0) const SizedBox(height: gap),
          Row(
            children: [
              for (var col = 0; col < columns; col++) ...[
                if (col > 0) const SizedBox(width: gap),
                Expanded(child: _chipFor(options[row * columns + col], otherLabel)),
              ],
            ],
          ),
        ],
      ],
    );
  }

  Widget _chipFor(_SourceOption source, String otherLabel) {
    final isOther = source.label == otherLabel;
    return _SourceChip(
      label: source.label,
      icon: source.icon,
      selected: _selectedSource == source.label,
      onTap: isOther ? _selectOther : () => _selectFixed(source.label),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Background area - takes remaining space for background image
        Expanded(child: Container()),

        // Bottom drawer card
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(32, 20, 32, 0),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
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
                const SizedBox(height: 20),
                _sourceGrid(context),
                AnimatedSize(
                  duration: const Duration(milliseconds: 260),
                  curve: Curves.easeInOut,
                  alignment: Alignment.center,
                  child: _isOtherSelected
                      ? Padding(
                          padding: const EdgeInsets.only(top: 10),
                          child: _OtherField(
                            controller: _otherController,
                            focusNode: _otherFocusNode,
                            onChanged: (_) => setState(() {}),
                            onClose: _deselectOther,
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _canContinue
                        ? () {
                            FocusManager.instance.primaryFocus?.unfocus();
                            final source = _isOtherSelected ? _otherController.text.trim() : _selectedSource!;
                            SharedPreferencesUtil().foundOmiSource = source;
                            updateUserOnboardingState(acquisitionSource: source);
                            PlatformManager.instance.analytics.onboardingUserAcquisitionSource(source);
                            widget.goNext();
                          }
                        : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: _canContinue ? Colors.white : Colors.grey[800],
                      foregroundColor: _canContinue ? Colors.black : Colors.grey[600],
                      disabledBackgroundColor: Colors.grey[800],
                      disabledForegroundColor: Colors.grey[600],
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.continueButton,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Equal-width capsule in the 4×3 source grid. Text scales down to fit so
/// longer labels (LinkedIn, App Store) don't overflow a column.
class _SourceChip extends StatelessWidget {
  final String label;
  final FaIconData icon;
  final bool selected;
  final VoidCallback onTap;

  const _SourceChip({required this.label, required this.icon, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        height: 44,
        padding: const EdgeInsets.symmetric(horizontal: 6),
        decoration: BoxDecoration(
          color: selected ? Colors.white : Colors.grey[900],
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: selected ? Colors.white : Colors.grey[700]!, width: 1),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            FaIcon(icon, size: 13, color: selected ? Colors.black : Colors.white),
            const SizedBox(width: 5),
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  label,
                  maxLines: 1,
                  style: TextStyle(
                    color: selected ? Colors.black : Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    fontFamily: 'Manrope',
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// What the "Other" chip turns into once tapped — a full-width capsule with
/// an inline text field, so specifying a source doesn't need a second box
/// appearing elsewhere on the page. Tapping the close icon collapses it back
/// into a plain chip.
class _OtherField extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onChanged;
  final VoidCallback onClose;

  const _OtherField({
    required this.controller,
    required this.focusNode,
    required this.onChanged,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.only(left: 20, right: 4),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.grey[700]!, width: 1),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              style: const TextStyle(color: Colors.white, fontSize: 15, fontFamily: 'Manrope'),
              decoration: InputDecoration(
                hintText: context.l10n.pleaseSpecify,
                hintStyle: TextStyle(color: Colors.grey[500], fontSize: 15, fontFamily: 'Manrope'),
                border: InputBorder.none,
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(vertical: 14),
              ),
              onChanged: onChanged,
            ),
          ),
          GestureDetector(
            onTap: onClose,
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Icon(Icons.close, size: 18, color: Colors.grey[500]),
            ),
          ),
        ],
      ),
    );
  }
}
