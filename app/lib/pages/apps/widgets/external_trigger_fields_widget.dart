import 'package:flutter/material.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/utils/other/validators.dart';
import 'package:provider/provider.dart';

class ExternalTriggerFieldsWidget extends StatelessWidget {
  const ExternalTriggerFieldsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (!provider.isCapabilitySelectedById('external_integration')) {
        return const SizedBox.shrink();
      }
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            height: 20,
          ),
          DropdownButtonFormField(
            value: provider.triggerEvent,
            decoration: InputDecoration(
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
                borderSide: BorderSide(
                  color: Colors.white,
                ),
              ),
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.api,
                      color: WidgetStateColor.resolveWith(
                          (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                  const SizedBox(
                    width: 8,
                  ),
                  const Text(
                    'Trigger Event',
                  ),
                ],
              ),
              labelStyle: const TextStyle(
                color: Colors.grey,
              ),
              floatingLabelStyle: const TextStyle(
                color: Colors.white,
              ),
            ),
            items: provider
                .getTriggerEvents()
                .map(
                  (event) => DropdownMenuItem(
                    value: event.id,
                    child: Text(event.title),
                  ),
                )
                .toList(),
            onChanged: provider.setTriggerEvent,
          ),
          const SizedBox(
            height: 20,
          ),
          TextFormField(
            controller: provider.authUrlController,
            validator: (value) {
              if (value != null) {
                if (value.isNotEmpty && !isValidUrl(value)) {
                  return 'Please enter a valid Auth URL';
                }
              }

              return null;
            },
            decoration: InputDecoration(
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
                borderSide: BorderSide(
                  color: Colors.white,
                ),
              ),
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.link,
                      color: WidgetStateColor.resolveWith(
                          (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                  const SizedBox(
                    width: 8,
                  ),
                  const Text(
                    'Auth URL (if required)',
                  ),
                ],
              ),
              hintText: 'https://your-auth-url.com/',
              labelStyle: const TextStyle(
                color: Colors.grey,
              ),
              floatingLabelStyle: const TextStyle(
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(
            height: 20,
          ),
          TextFormField(
            controller: provider.webhookUrlController,
            validator: (value) {
              if (value == null || !isValidUrl(value)) {
                return 'Please enter a valid webhook URL';
              }
              return null;
            },
            decoration: InputDecoration(
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
                borderSide: BorderSide(
                  color: Colors.white,
                ),
              ),
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.link,
                      color: WidgetStateColor.resolveWith(
                          (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                  const SizedBox(
                    width: 8,
                  ),
                  const Text(
                    'Webhook URL',
                  ),
                ],
              ),
              hintText: 'https://your-webhook-url.com/',
              labelStyle: const TextStyle(
                color: Colors.grey,
              ),
              floatingLabelStyle: const TextStyle(
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(
            height: 20,
          ),
          TextFormField(
            controller: provider.setupCompletedController,
            validator: (value) {
              if (value != null) {
                if (value.isNotEmpty && !isValidUrl(value)) {
                  return 'Please enter a valid URL';
                }
              }

              return null;
            },
            decoration: InputDecoration(
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
                borderSide: BorderSide(
                  color: Colors.white,
                ),
              ),
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.verified_user_rounded,
                      color: WidgetStateColor.resolveWith(
                          (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                  const SizedBox(
                    width: 8,
                  ),
                  const Text(
                    'Setup Completed URL',
                  ),
                ],
              ),
              hintText: 'https://your-setup-completed-url.com/',
              labelStyle: const TextStyle(
                color: Colors.grey,
              ),
              floatingLabelStyle: const TextStyle(
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(
            height: 20,
          ),
          TextFormField(
            maxLines: null,
            controller: provider.instructionsController,
            decoration: InputDecoration(
              border: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(10)),
                borderSide: BorderSide(
                  color: Colors.white,
                ),
              ),
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.integration_instructions,
                      color: WidgetStateColor.resolveWith(
                          (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                  const SizedBox(
                    width: 8,
                  ),
                  const Text(
                    'Setup Instructions',
                  ),
                ],
              ),
              hintText: 'Link or text instructions for app setup',
              labelStyle: const TextStyle(
                color: Colors.grey,
              ),
              floatingLabelStyle: const TextStyle(
                color: Colors.white,
              ),
            ),
          ),
        ],
      );
    });
  }
}
