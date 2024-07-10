import 'package:flutter/material.dart';

class InstructionsTab extends StatefulWidget {
  final VoidCallback goNext;
  final bool deviceFound;

  const InstructionsTab({super.key, required this.goNext, required this.deviceFound});

  @override
  State<InstructionsTab> createState() => _InstructionsTabState();
}

class _InstructionsTabState extends State<InstructionsTab> {
  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: BorderRadius.circular(24),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
          margin: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Center(
                child: Text(
                  'Set Up Instructions',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Record samples of your voice to create a speech profile. This will help the device recognise your voice.',
                style: TextStyle(color: Colors.grey, fontSize: 16),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Image.asset(
                'assets/images/instruction_1.png',
                height: 40,
              ),
              const SizedBox(height: 8),
              const Text(
                'Wear the device and make sure it is connected to the app ',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 16),
              Image.asset(
                'assets/images/instruction_2.png',
                width: 40,
                height: 40,
              ),
              const SizedBox(height: 8),
              const Text(
                'Make sure you’re in a quiet environment',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 16),
              Image.asset(
                'assets/images/instruction_3.png',
                width: 40,
                height: 40,
              ),
              const SizedBox(height: 8),
              const Text(
                'Repeat the phrases that will appear on the screen',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ],
          ),
        ),
        widget.deviceFound
            ? Row(
                children: [
                  Expanded(
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                      child: MaterialButton(
                        onPressed: () {
                          // if (SharedPreferencesUtil().recordingsLanguage != 'en') {
                          //   showDialog(
                          //     context: context,
                          //     barrierDismissible: false,
                          //     builder: (c) => getDialog(
                          //       context,
                          //       () {
                          //         Navigator.of(context).pop();
                          //       },
                          //       widget.goNext,
                          //       'Speech profiles not available',
                          //       'Speech profiles are only available for English language. You can still set it up,'
                          //           ' but it will not work with ${getLanguageName(SharedPreferencesUtil().recordingsLanguage)} language.',
                          //       singleButton: false,
                          //       okButtonText: 'Continue',
                          //     ),
                          //   );
                          // }
                          widget.goNext();
                        },
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: const BorderSide(color: Colors.white, width: 1),
                        ),
                        color: Theme.of(context).colorScheme.primary,
                        child: const Padding(
                          padding: EdgeInsets.all(16.0),
                          child: Text(
                            'Start',
                            style: TextStyle(color: Colors.white, fontSize: 20),
                          ),
                        ),
                      ),
                    ),
                  )
                ],
              )
            : const SizedBox()
      ],
    );
  }
}
