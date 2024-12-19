import 'package:flutter/material.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/utils/other/validators.dart';
import 'package:provider/provider.dart';

class NotificationsHistoryWebhookField extends StatelessWidget {
  const NotificationsHistoryWebhookField({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (!provider.isCapabilitySelectedById('proactive_notification')) {
        return const SizedBox.shrink();
      }
      return Column(
        children: [
          const SizedBox(
            height: 12,
          ),
          Container(
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
                    'Notifications History Webhook URL (Optional)',
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
                      if (value != null && value.isNotEmpty && !isValidUrl(value)) {
                        return 'Please enter a valid URL';
                      }
                      return null;
                    },
                    controller: provider.notificationsHistoryWebhookController,
                    decoration: const InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      hintText: 'https://your-domain.com/notifications-webhook',
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.only(left: 8.0, top: 4.0),
                  child: Text(
                    'Receive notifications sent by this app to users',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ],
      );
    });
  }
} 