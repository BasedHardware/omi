import 'package:flutter/material.dart';
import 'package:friend_private/services/translation_service.dart';

class InfoButton extends StatefulWidget {
  const InfoButton({super.key});

  @override
  State<InfoButton> createState() => _InfoButtonState();
}

class _InfoButtonState extends State<InfoButton> {
  @override
  Widget build(BuildContext context) {
    return TextButton(
        onPressed: () {
          showDialog(
              context: context,
              builder: (context) => AlertDialog(
                    backgroundColor: Theme.of(context).primaryColor,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(15.0),
                    ),
                    titlePadding: const EdgeInsets.only(top: 20, left: 20, right: 20),
                    contentPadding: const EdgeInsets.all(20),
                    actionsPadding: const EdgeInsets.only(bottom: 8, right: 12),
                    title:  Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                    TranslationService.translate('How Friend Works?'),
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        // IconButton(
                        //   icon: const Icon(Icons.close, color: Colors.white),
                        //   onPressed: () => Navigator.of(context).pop(),
                        // ),
                      ],
                    ),
                    content:  Text(
                      TranslationService.translate("Ready to chat? Your transcripts will pop up here as you start talking. "
                      "If Friend notices you’ve been quiet for 2 minutes, it’ll wrap up "
                      "the conversation and start crafting your memory. You can find all your "
                      "treasured moments in the Memories tab!"),
                      style: TextStyle(
                        color: Colors.white,
                        height: 1.5,
                      ),
                    ),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.of(context).pop(),
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                          backgroundColor: Colors.purpleAccent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10.0),
                          ),
                        ),
                        child: Text(
                        TranslationService.translate('Got it!'),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ));
        },
        child: Text(
        TranslationService.translate('How Friend works?'),
          style: TextStyle(decoration: TextDecoration.underline, color: Colors.white, fontSize: 15),
        ));
  }
}
