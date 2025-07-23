import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:omi/utils/platform/platform_service.dart';

class NameWidget extends StatefulWidget {
  final Function goNext;

  const NameWidget({super.key, required this.goNext});

  @override
  State<NameWidget> createState() => _NameWidgetState();
}

class _NameWidgetState extends State<NameWidget> {
  late TextEditingController nameController;
  var focusNode = FocusNode();

  @override
  void initState() {
    nameController = TextEditingController(text: SharedPreferencesUtil().givenName);
    super.initState();

    // Auto-focus the name input field after the widget is built
    // WidgetsBinding.instance.addPostFrameCallback((_) {
    //   focusNode.requestFocus();
    // });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Background area - takes remaining space
        Expanded(
          child: Container(), // Just takes up space for background image
        ),

        // Bottom drawer card - wraps content
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(32, 26, 32, MediaQuery.of(context).padding.bottom + 8),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(40),
              topRight: Radius.circular(40),
            ),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 16),

                // Main title
                const Text(
                  'What\'s your name?',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 8),

                // // Subtitle
                // Text(
                //   'Tell us how you\'d like to be addressed.\nThis helps personalize your Omi experience.',
                //   style: TextStyle(
                //     color: Colors.white.withOpacity(0.6),
                //     fontSize: 16,
                //     fontFamily: 'Manrope',
                //     height: 1.5,
                //   ),
                //   textAlign: TextAlign.center,
                // ),

                const SizedBox(height: 28),

                // Name input field
                Container(
                  decoration: BoxDecoration(
                    color: Colors.grey[900],
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: Colors.grey[700]!,
                      width: 1,
                    ),
                  ),
                  child: TextField(
                    controller: nameController,
                    focusNode: focusNode,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontFamily: 'Manrope',
                      fontWeight: FontWeight.w500,
                    ),
                    textAlign: TextAlign.center,
                    decoration: InputDecoration(
                      hintText: 'Enter your name',
                      hintStyle: TextStyle(
                        color: Colors.grey[500],
                        fontSize: 18,
                        fontFamily: 'Manrope',
                      ),
                      border: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 24,
                        vertical: 20,
                      ),
                    ),
                    onChanged: (value) {
                      setState(() {}); // Trigger rebuild to update button state
                    },
                  ),
                ),

                const SizedBox(height: 32),

                // Continue button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: nameController.text.trim().isEmpty
                        ? null
                        : () async {
                            FocusManager.instance.primaryFocus?.unfocus();
                            updateGivenName(nameController.text.trim());
                            widget.goNext();
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: nameController.text.trim().isEmpty ? Colors.grey[800] : Colors.white,
                      foregroundColor: nameController.text.trim().isEmpty ? Colors.grey[600] : Colors.black,
                      disabledBackgroundColor: Colors.grey[800],
                      disabledForegroundColor: Colors.grey[600],
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      elevation: 0,
                    ),
                    child: const Text(
                      'Continue',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        fontFamily: 'Manrope',
                      ),
                    ),
                  ),
                ),

                // const SizedBox(height: 24),

                // // Need Help link
                // PlatformService.isIntercomSupported
                //     ? InkWell(
                //         onTap: () {
                //           Intercom.instance.displayMessenger();
                //         },
                //         child: Text(
                //           'Need Help?',
                //           style: TextStyle(
                //             color: Colors.white.withOpacity(0.6),
                //             fontSize: 14,
                //             fontFamily: 'Manrope',
                //             decoration: TextDecoration.underline,
                //           ),
                //         ),
                //       )
                //     : const SizedBox.shrink(),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
