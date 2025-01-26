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
      return GestureDetector(
        onTap: () {
          FocusScope.of(context).unfocus();
        },
        child: Column(
          children: [
            const SizedBox(
              height: 12,
            ),
            Form(
              key: provider.externalIntegrationKey,
              onChanged: () {
                provider.checkValidity();
              },
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(12.0),
                ),
                padding: const EdgeInsets.all(14.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(left: 8.0),
                      child: Text(
                        'Trigger Event',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
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
                                        itemCount: provider.getTriggerEvents().length,
                                        physics: const NeverScrollableScrollPhysics(),
                                        itemBuilder: (context, index) {
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
                        margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                        padding: const EdgeInsets.symmetric(horizontal: 2.0, vertical: 10.0),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade800,
                          borderRadius: BorderRadius.circular(10.0),
                        ),
                        width: double.infinity,
                        child: Row(
                          children: [
                            const SizedBox(
                              width: 12,
                            ),
                            Text(
                              provider.mapTriggerEventIdToName(provider.triggerEvent) ?? 'None Selected',
                              style: TextStyle(
                                  color: provider.triggerEvent != null ? Colors.grey.shade100 : Colors.grey.shade400,
                                  fontSize: 16),
                            ),
                            const Spacer(),
                            Icon(
                              Icons.arrow_forward_ios_rounded,
                              color: Colors.grey.shade400,
                            ),
                            const SizedBox(
                              width: 12,
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(
                      height: 16,
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 8.0),
                      child: Text(
                        'Auth URL (if required)',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                      margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      width: double.infinity,
                      child: TextFormField(
                        controller: provider.authUrlController,
                        decoration: const InputDecoration(
                          isDense: true,
                          border: InputBorder.none,
                          hintText: 'https://your-auth-url.com/',
                        ),
                      ),
                    ),
                    const SizedBox(
                      height: 16,
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 8.0),
                      child: Text(
                        'Webhook URL',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                      margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      width: double.infinity,
                      child: TextFormField(
                        validator: (value) {
                          if (value == null || !isValidUrl(value)) {
                            return 'Please enter a valid webhook URL';
                          }
                          return null;
                        },
                        controller: provider.webhookUrlController,
                        decoration: InputDecoration(
                          isDense: true,
                          errorStyle: TextStyle(color: Colors.red.shade100),
                          border: InputBorder.none,
                          hintText: 'https://your-webhook-url.com/',
                        ),
                      ),
                    ),
                    const SizedBox(
                      height: 16,
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 8.0),
                      child: Text(
                        'Setup Completed URL (optional)',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                      margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      width: double.infinity,
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
                        decoration: const InputDecoration(
                          isDense: true,
                          border: InputBorder.none,
                          hintText: 'https://your-setup-completed-url.com/',
                        ),
                      ),
                    ),
                    const SizedBox(
                      height: 16,
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 8.0),
                      child: Text(
                        'Setup Instructions',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                      margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      width: double.infinity,
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          minHeight: MediaQuery.sizeOf(context).height * 0.1,
                          maxHeight: MediaQuery.sizeOf(context).height * 0.4,
                        ),
                        child: Scrollbar(
                          child: SingleChildScrollView(
                            scrollDirection: Axis.vertical,
                            reverse: false,
                            child: TextFormField(
                              controller: provider.instructionsController,
                              maxLines: null,
                              decoration: const InputDecoration(
                                contentPadding: EdgeInsets.only(top: 6, bottom: 2),
                                isDense: true,
                                border: InputBorder.none,
                                hintText: 'Link or text instructions for app setup',
                                hintMaxLines: 4,
                              ),
                            ),
                          ),
                        ),
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
