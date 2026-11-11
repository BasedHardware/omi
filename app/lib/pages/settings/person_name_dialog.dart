import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Adds a person, or renames [person] when given.
Future<void> showPersonNameDialog(BuildContext context, PeopleProvider provider, {Person? person}) async {
  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
  if (!connectivityProvider.isConnected) {
    ConnectivityProvider.showNoInternetDialog(context);
    return;
  }

  final nameController = TextEditingController(text: person?.name ?? '');
  final formKey = GlobalKey<FormState>();

  await showDialog(
    context: context,
    builder: (dialogContext) => OmiAlertDialog(
      title: person == null ? context.l10n.addNewPerson : context.l10n.editPerson,
      content: _form(dialogContext, formKey, nameController),
      actions: [
        OmiDialogAction(label: context.l10n.cancel, onPressed: () => Navigator.pop(dialogContext)),
        OmiDialogAction(
          label: person == null ? context.l10n.add : context.l10n.save,
          isDefault: true,
          onPressed: () {
            if (formKey.currentState!.validate()) {
              final text = nameController.text;
              final name = text[0].toUpperCase() + text.substring(1);
              if (person == null) {
                provider.createPersonProvider(name);
              } else {
                provider.updatePersonProvider(person, name);
              }
              Navigator.pop(dialogContext);
            }
          },
        ),
      ],
    ),
  );
}

Widget _form(BuildContext context, GlobalKey<FormState> formKey, TextEditingController nameController) {
  return omiUsesCupertinoDialogs(context)
      ? Material(
          color: Colors.transparent,
          child: Theme(
            data: ThemeData(
              textSelectionTheme: TextSelectionThemeData(
                cursorColor: OmiColors.textPrimary,
                selectionColor: OmiColors.textPrimary.withValues(alpha: 0.24),
                selectionHandleColor: OmiColors.textPrimary,
              ),
            ),
            child: Form(
              key: formKey,
              child: CupertinoTextFormFieldRow(
                padding: const EdgeInsets.only(top: 16),
                controller: nameController,
                placeholder: context.l10n.name,
                keyboardType: TextInputType.name,
                textCapitalization: TextCapitalization.words,
                placeholderStyle: TextStyle(color: OmiColors.textTertiary),
                style: TextStyle(color: OmiColors.textPrimary),
                validator: _nameValidator(context),
              ),
            ),
          ),
        )
      : Form(
          key: formKey,
          child: TextFormField(
            controller: nameController,
            keyboardType: TextInputType.name,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(
              labelText: context.l10n.name,
              labelStyle: TextStyle(color: OmiColors.textPrimary),
              focusColor: OmiColors.textPrimary,
              focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: OmiColors.border)),
            ),
            validator: _nameValidator(context),
          ),
        );
}

String? Function(String?) _nameValidator(BuildContext context) {
  return (String? value) {
    if (value == null || value.isEmpty) {
      return context.l10n.pleaseEnterName;
    }
    if (value.length < 2 || value.length > 40) {
      return context.l10n.nameMustBeBetweenCharacters;
    }
    return null;
  };
}
