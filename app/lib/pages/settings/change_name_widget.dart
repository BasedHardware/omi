import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The "Edit Name" dialog, shown with `showDialog(builder: (_) => const ChangeNameWidget())`.
class ChangeNameWidget extends StatefulWidget {
  const ChangeNameWidget({super.key});

  @override
  State<ChangeNameWidget> createState() => _ChangeNameWidgetState();
}

class _ChangeNameWidgetState extends State<ChangeNameWidget> {
  late TextEditingController nameController;
  User? user;
  bool isSaving = false;

  @override
  void initState() {
    user = AuthService.instance.getFirebaseUser();
    nameController = TextEditingController(
      text: SharedPreferencesUtil().givenName.isNotEmpty ? SharedPreferencesUtil().givenName : user?.displayName ?? '',
    );
    nameController.addListener(_onNameChanged);
    super.initState();
  }

  @override
  void dispose() {
    nameController.removeListener(_onNameChanged);
    nameController.dispose();
    super.dispose();
  }

  void _onNameChanged() => setState(() {});

  bool get _canSave => !isSaving && nameController.text.trim().isNotEmpty;

  void _save() {
    final name = nameController.text.trim();
    if (name.isEmpty) return;
    setState(() => isSaving = true);
    SharedPreferencesUtil().givenName = name;
    AuthService.instance.updateGivenName(name);
    OmiFeedback.confirm(context, context.l10n.nameUpdatedSuccessfully);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return OmiAlertDialog(
      title: context.l10n.editName,
      message: context.l10n.howShouldOmiCallYou,
      // The Cupertino dialog has no Material ancestor; the text field needs one.
      content: Material(
        type: MaterialType.transparency,
        child: TextField(
          controller: nameController,
          autofocus: true,
          enabled: !isSaving,
          textCapitalization: TextCapitalization.words,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) {
            if (_canSave) _save();
          },
          style: OmiType.body,
          decoration: InputDecoration(
            hintText: context.l10n.enterYourName,
            hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
            filled: true,
            fillColor: OmiColors.surface2,
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
            border: const OutlineInputBorder(borderRadius: OmiRadius.smAll, borderSide: BorderSide.none),
            enabledBorder: const OutlineInputBorder(borderRadius: OmiRadius.smAll, borderSide: BorderSide.none),
            focusedBorder: const OutlineInputBorder(
              borderRadius: OmiRadius.smAll,
              borderSide: BorderSide(color: OmiColors.textTertiary),
            ),
          ),
        ),
      ),
      actions: [
        OmiDialogAction(label: context.l10n.cancel, onPressed: () => Navigator.of(context).pop()),
        OmiDialogAction(
          label: isSaving ? context.l10n.saving : context.l10n.save,
          isDefault: true,
          onPressed: _canSave ? _save : null,
        ),
      ],
    );
  }
}
