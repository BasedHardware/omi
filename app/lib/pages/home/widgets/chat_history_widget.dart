import 'package:flutter/material.dart';
import 'package:friend_private/pages/chat_history/page.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class ChatHistoryWidget extends StatelessWidget {
  const ChatHistoryWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 1, // Only show in chat page
      builder: (context, isChatPage, child) {
        if (!isChatPage) {
          return const SizedBox.shrink();
        }

        return GestureDetector(
          onTap: () {
            routeToPage(context, const ChatHistoryPage());
            MixpanelManager().pageOpened('Chat History');
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.history,
                  color: Colors.white,
                  size: MediaQuery.sizeOf(context).width * 0.05,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}