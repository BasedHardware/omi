import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_plain_step.dart';
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

    // The step opens with the keyboard up, ready to type.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) focusNode.requestFocus();
    });
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
    return OnboardingPlainStep(
      title: context.l10n.whatsYourName,
      centered: true,
      body: DecoratedBox(
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: TextField(
          controller: nameController,
          focusNode: focusNode,
          style: OmiType.title3,
          textAlign: TextAlign.center,
          textCapitalization: TextCapitalization.words,
          textInputAction: TextInputAction.done,
          autocorrect: false,
          cursorColor: OmiColors.textPrimary,
          onSubmitted: (_) => _submit(),
          // Keep the keyboard up when a finger lands outside the field, so a tap on Continue lands on
          // Continue instead of only closing the keyboard (and moving the button). Tapping empty
          // space still closes it through the onboarding host.
          onTapOutside: (_) {},
          decoration: InputDecoration(
            hintText: context.l10n.enterYourName,
            hintStyle: OmiType.title3.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w400),
            border: InputBorder.none,
            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: OmiSpacing.lg),
          ),
          onChanged: (value) {
            setState(() {}); // Trigger rebuild to update button state
          },
        ),
      ),
      action: OmiButton(
        key: const Key('onboarding_name_continue'),
        label: context.l10n.continueButton,
        expand: true,
        onPressed: _canContinue ? _submit : null,
      ),
    );
  }
}
