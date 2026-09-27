import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/action_fields_widget.dart';
import 'package:omi/pages/apps/widgets/app_form_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/validators.dart';

class ExternalTriggerFieldsWidget extends StatelessWidget {
  const ExternalTriggerFieldsWidget({super.key});

  static const _docsUrl = 'https://docs.omi.me/doc/developer/apps/Integrations';

  void _pickTriggerEvent(BuildContext context, AddAppProvider provider) {
    final events = provider.getTriggerEvents();
    showAppOptionPicker<String?>(
      context: context,
      title: context.l10n.triggerEvents,
      options: [
        for (final event in events) AppFormOption<String?>(event.id, event.getLocalizedTitle(context)),
        AppFormOption<String?>(null, context.l10n.sttNone),
      ],
      selected: provider.triggerEvent,
      onSelected: provider.setTriggerEvent,
    );
  }

  String? _selectedEventTitle(BuildContext context, AddAppProvider provider) {
    final id = provider.triggerEvent;
    if (id == null) return null;
    for (final event in provider.getTriggerEvents()) {
      if (event.id == id) return event.getLocalizedTitle(context);
    }
    return provider.mapTriggerEventIdToName(id);
  }

  String? _validateOptionalUrl(BuildContext context, String? value) {
    if (value != null && value.isNotEmpty && !isValidUrl(value)) return context.l10n.invalidUrlError;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        if (!provider.isCapabilitySelectedById('external_integration')) {
          return const SizedBox.shrink();
        }
        final l10n = context.l10n;

        Widget field(Widget child) => Padding(
              padding: const EdgeInsets.only(left: 10.0, right: 10.0, top: OmiSpacing.md),
              child: child,
            );

        return GestureDetector(
          onTap: () {
            FocusScope.of(context).unfocus();
          },
          child: Column(
            children: [
              // Scopes Card
              const SizedBox(height: 18),
              const AppFormCard(child: Padding(padding: EdgeInsets.only(left: 2.0), child: ActionFieldsWidget())),

              // External Integration Card
              const SizedBox(height: 18),
              Form(
                key: provider.externalIntegrationKey,
                onChanged: () {
                  provider.checkValidity();
                },
                child: AppFormCard(
                  padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 20.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(left: 10.0, right: 0, bottom: OmiSpacing.xs),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            AppFormSectionTitle(l10n.capabilityExternalIntegration),
                            const AppFormDocsButton(url: _docsUrl),
                          ],
                        ),
                      ),
                      AppFormSelectorField(
                        margin: const EdgeInsets.only(left: 10.0, right: 10.0, top: 10, bottom: 6),
                        value: _selectedEventTitle(context, provider),
                        placeholder: l10n.triggerEvent,
                        onTap: () => _pickTriggerEvent(context, provider),
                      ),
                      // Only show the webhook field once a trigger event is selected
                      if (provider.triggerEvent != null)
                        field(
                          TextFormField(
                            validator: (value) {
                              if (provider.triggerEvent != null && (value == null || !isValidUrl(value))) {
                                return l10n.invalidWebhookUrlError;
                              }
                              return null;
                            },
                            controller: provider.webhookUrlController,
                            decoration: appFormInputDecoration(label: '${l10n.webhookUrl}*'),
                          ),
                        ),
                      field(
                        TextFormField(
                          validator: (value) => _validateOptionalUrl(context, value),
                          controller: provider.appHomeUrlController,
                          decoration: appFormInputDecoration(label: l10n.appHomeUrl),
                        ),
                      ),
                      field(
                        TextFormField(
                          controller: provider.instructionsController,
                          maxLines: null,
                          minLines: 3,
                          decoration: appFormInputDecoration(label: l10n.setupInstructions, alignLabelWithHint: true),
                        ),
                      ),
                      field(
                        TextFormField(
                          controller: provider.authUrlController,
                          decoration: appFormInputDecoration(label: l10n.authUrl),
                        ),
                      ),
                      field(
                        TextFormField(
                          validator: (value) => _validateOptionalUrl(context, value),
                          controller: provider.setupCompletedController,
                          decoration: appFormInputDecoration(label: l10n.setupCompletedUrl),
                        ),
                      ),
                      field(
                        TextFormField(
                          validator: (value) => _validateOptionalUrl(context, value),
                          controller: provider.chatToolsManifestUrlController,
                          decoration: appFormInputDecoration(label: l10n.chatToolsManifestUrl),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
