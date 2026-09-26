import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class NameWidget extends StatefulWidget {
  final Function goNext;

  const NameWidget({super.key, required this.goNext});

  @override
  State<NameWidget> createState() => _NameWidgetState();
}

class _NameWidgetState extends State<NameWidget> {
  late TextEditingController nameController;
  var focusNode = FocusNode();

  @override
  void initState() {
    nameController = TextEditingController(text: SharedPreferencesUtil().givenName);
    super.initState();

    // Auto-focus the name input field after the widget is built
    // WidgetsBinding.instance.addPostFrameCallback((_) {
    //   focusNode.requestFocus();
    // });
  }

  @override
  void dispose() {
    nameController.dispose();
    focusNode.dispose();
    super.dispose();
  }

  bool get _canContinue => nameController.text.trim().isNotEmpty;

  void _submit() {
    if (!_canContinue) return;
    FocusManager.instance.primaryFocus?.unfocus();
    AuthService.instance.updateGivenName(nameController.text.trim());
    OmiHaptics.selection();
    widget.goNext();
  }

  @override
  Widget build(BuildContext context) {
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          OnboardingHeader(title: context.l10n.whatShouldOmiCallYou),
          const SizedBox(height: OmiSpacing.lg),
          // v2: a large field on a card, the name in 22pt bold.
          Container(
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
            child: TextField(
              controller: nameController,
              focusNode: focusNode,
              style: OmiType.title2,
              textCapitalization: TextCapitalization.words,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submit(),
              decoration: InputDecoration(
                hintText: context.l10n.yourNamePlaceholder,
                hintStyle: OmiType.title2.copyWith(color: OmiColors.textTertiary),
                border: InputBorder.none,
                contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.md),
              ),
              onChanged: (value) {
                setState(() {}); // Trigger rebuild to update button state
              },
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          Padding(
            padding: OnboardingCard.textInset,
            child: Text(context.l10n.nameUsageHint, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.xxl),
          OmiButton(
            key: const Key('onboarding_name_continue'),
            label: context.l10n.continueButton,
            expand: true,
            onPressed: _canContinue ? _submit : null,
          ),
        ],
      ),
    );
  }
}
