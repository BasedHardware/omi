import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/action_fields_widget.dart';
import 'package:omi/utils/other/validators.dart';

class ExternalTriggerFieldsWidget extends StatelessWidget {
  const ExternalTriggerFieldsWidget({super.key});

  InputDecoration _buildInputDecoration(String label, {bool alignLabelWithHint = false}) {
    return InputDecoration(
      labelText: label,
      labelStyle: TextStyle(color: Colors.grey.shade400),
      floatingLabelStyle: TextStyle(color: Colors.grey.shade300),
      alignLabelWithHint: alignLabelWithHint,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 16.0),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12.0),
        borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12.0),
        borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12.0),
        borderSide: BorderSide(color: Colors.grey.shade400, width: 1),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12.0),
        borderSide: BorderSide(color: Colors.red.shade300, width: 1),
      ),
      filled: false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (!provider.isCapabilitySelectedById('external_integration')) {
        return const SizedBox.shrink();
      }

      return GestureDetector(
        onTap: () {
          FocusScope.of(context).unfocus();
        },
        child: Column(
          children: [
            // Scopes Card
            const SizedBox(height: 18),
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(18.0),
              ),
              padding: const EdgeInsets.all(14.0),
              child: const Padding(
                padding: EdgeInsets.only(left: 2.0),
                child: ActionFieldsWidget(),
              ),
            ),

            // External Integration Card
            const SizedBox(height: 18),
            Form(
              key: provider.externalIntegrationKey,
              onChanged: () {
                provider.checkValidity();
              },
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(18.0),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 20.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0, bottom: 12.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'External Integration',
                            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                          ),
                          GestureDetector(
                            onTap: () {
                              launchUrl(Uri.parse('https://docs.omi.me/doc/developer/apps/Integrations'));
                            },
                            child: FaIcon(
                              FontAwesomeIcons.solidCircleQuestion,
                              color: Colors.grey.shade500,
                              size: 18,
                            ),
                          ),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: () {
                        showModalBottomSheet(
                          context: context,
                          isScrollControlled: false,
                          shape: const RoundedRectangleBorder(
                            borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                          ),
                          builder: (context) {
                            return Consumer<AddAppProvider>(builder: (context, provider, child) {
                              return Container(
                                padding: const EdgeInsets.all(16.0),
                                height: MediaQuery.of(context).size.height * 0.6,
                                child: SingleChildScrollView(
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const SizedBox(
                                        height: 12,
                                      ),
                                      const Text(
                                        'Trigger Events',
                                        style: TextStyle(color: Colors.white, fontSize: 18),
                                      ),
                                      const SizedBox(
                                        height: 18,
                                      ),
                                      ListView.separated(
                                        separatorBuilder: (context, index) {
                                          return Divider(
                                            color: Colors.grey.shade600,
                                            height: 1,
                                          );
                                        },
                                        shrinkWrap: true,
                                        itemCount: provider.getTriggerEvents().length + 1, // +1 for None option
                                        physics: const NeverScrollableScrollPhysics(),
                                        itemBuilder: (context, index) {
                                          // Special case for "None" option at the end
                                          if (index == provider.getTriggerEvents().length) {
                                            return InkWell(
                                              onTap: () {
                                                provider.setTriggerEvent(null);
                                                Navigator.pop(context);
                                              },
                                              child: Container(
                                                padding: const EdgeInsets.symmetric(vertical: 10),
                                                child: Row(
                                                  crossAxisAlignment: CrossAxisAlignment.center,
                                                  children: [
                                                    const SizedBox(
                                                      width: 6,
                                                    ),
                                                    Text(
                                                      "None",
                                                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                                    ),
                                                    const Spacer(),
                                                    Checkbox(
                                                      value: provider.triggerEvent == null,
                                                      onChanged: (value) {
                                                        provider.setTriggerEvent(null);
                                                        Navigator.pop(context);
                                                      },
                                                      side: BorderSide(color: Colors.grey.shade300),
                                                      shape: const CircleBorder(),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            );
                                          }
                                          return InkWell(
                                            onTap: () {
                                              provider.setTriggerEvent(provider.getTriggerEvents()[index].id);
                                              Navigator.pop(context);
                                            },
                                            child: Container(
                                              padding: const EdgeInsets.symmetric(vertical: 10),
                                              child: Row(
                                                crossAxisAlignment: CrossAxisAlignment.center,
                                                children: [
                                                  const SizedBox(
                                                    width: 6,
                                                  ),
                                                  Text(
                                                    provider.getTriggerEvents()[index].title,
                                                    style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                                  ),
                                                  const Spacer(),
                                                  Checkbox(
                                                    value:
                                                        provider.triggerEvent == provider.getTriggerEvents()[index].id,
                                                    onChanged: (value) {
                                                      provider.setTriggerEvent(provider.getTriggerEvents()[index].id);
                                                    },
                                                    side: BorderSide(color: Colors.grey.shade300),
                                                    shape: const CircleBorder(),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          );
                                        },
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            });
                          },
                        );
                      },
                      child: Container(
                        margin: const EdgeInsets.only(left: 10.0, right: 10.0, top: 10, bottom: 6),
                        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 16.0),
                        decoration: BoxDecoration(
                          color: Colors.transparent,
                          borderRadius: BorderRadius.circular(12.0),
                          border: Border.all(color: Colors.grey.withOpacity(0.3), width: 1),
                        ),
                        width: double.infinity,
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                provider.mapTriggerEventIdToName(provider.triggerEvent) ?? 'Trigger Event',
                                style: TextStyle(
                                    color: provider.triggerEvent != null ? Colors.grey.shade100 : Colors.grey.shade400,
                                    fontSize: 16),
                              ),
                            ),
                            FaIcon(
                              FontAwesomeIcons.chevronRight,
                              color: Colors.grey.shade400,
                              size: 14,
                            ),
                          ],
                        ),
                      ),
                    ),
                    // Only show the rest of the form if a trigger event is selected
                    if (provider.triggerEvent != null) ...[
                      const SizedBox(height: 16),
                      Padding(
                        padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                        child: TextFormField(
                          validator: (value) {
                            if (provider.triggerEvent != null && (value == null || !isValidUrl(value))) {
                              return 'Please enter a valid webhook URL';
                            }
                            return null;
                          },
                          controller: provider.webhookUrlController,
                          decoration: _buildInputDecoration('Webhook URL*'),
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                      child: TextFormField(
                        validator: (value) {
                          if (value != null && value.isNotEmpty && !isValidUrl(value)) {
                            return 'Please enter a valid URL';
                          }
                          return null;
                        },
                        controller: provider.appHomeUrlController,
                        decoration: _buildInputDecoration('App Home URL'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                      child: TextFormField(
                        controller: provider.instructionsController,
                        maxLines: null,
                        minLines: 3,
                        decoration: _buildInputDecoration('Setup Instructions', alignLabelWithHint: true),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                      child: TextFormField(
                        controller: provider.authUrlController,
                        decoration: _buildInputDecoration('Auth URL'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                      child: TextFormField(
                        validator: (value) {
                          if (value != null) {
                            if (value.isNotEmpty && !isValidUrl(value)) {
                              return 'Please enter a valid URL';
                            }
                          }
                          return null;
                        },
                        controller: provider.setupCompletedController,
                        decoration: _buildInputDecoration('Setup Completed URL'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.only(left: 10.0, right: 10.0),
                      child: TextFormField(
                        validator: (value) {
                          if (value != null && value.isNotEmpty && !isValidUrl(value)) {
                            return 'Please enter a valid URL';
                          }
                          return null;
                        },
                        controller: provider.chatToolsManifestUrlController,
                        decoration: _buildInputDecoration('Chat Tools Manifest URL'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
    });
  }
}
