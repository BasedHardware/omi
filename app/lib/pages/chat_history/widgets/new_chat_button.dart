import 'package:flutter/material.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:provider/provider.dart';

class NewChatButton extends StatelessWidget {
  const NewChatButton({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Consumer<AppProvider>(builder: (context, provider, child) {
        return ElevatedButton(
        onPressed: () async {
          await context.read<MessageProvider>().createNewChat();
          var app = provider.getSelectedApp();
          if (context.read<MessageProvider>().messages.isEmpty) {
            context.read<MessageProvider>().sendInitialAppMessage(app);
          }
          Navigator.pop(context);
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: Theme.of(context).primaryColor,
          minimumSize: const Size(double.infinity, 50),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.add_circle_outline, color: Colors.white),
            SizedBox(width: 8),
            Text(
              'New Chat',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        );
      }) ,
    );
  }
}