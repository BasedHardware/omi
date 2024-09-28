import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

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
    // focusNode.requestFocus();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            'How should Omi call you?',
            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
            textAlign: TextAlign.start,
          ),
          const SizedBox(height: 24),
          TextField(
            enabled: true,
            focusNode: focusNode,
            controller: nameController,
            obscureText: false,
            textAlign: TextAlign.center,
            textAlignVertical: TextAlignVertical.center,
            decoration: InputDecoration(
              hintText: 'How Omi should call you?',
              hintStyle: const TextStyle(fontSize: 14, color: Colors.grey),
              border: GradientOutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                gradient: const LinearGradient(
                  colors: <Color>[
                    Color.fromARGB(255, 202, 201, 201),
                    Color.fromARGB(255, 159, 158, 158),
                  ],
                ),
              ),
            ),
            style: TextStyle(fontSize: 16, color: Colors.grey.shade200),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    border: const GradientBoxBorder(
                      gradient: LinearGradient(colors: [
                        Color.fromARGB(127, 208, 208, 208),
                        Color.fromARGB(127, 188, 99, 121),
                        Color.fromARGB(127, 86, 101, 182),
                        Color.fromARGB(127, 126, 190, 236)
                      ]),
                      width: 2,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: MaterialButton(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                    onPressed: () async {
                      if (nameController.text.isEmpty || nameController.text.trim().isEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Please enter a valid name')),
                        );
                      } else {
                        FocusManager.instance.primaryFocus?.unfocus();
                        updateGivenName(nameController.text);
                        widget.goNext();
                      }
                    },
                    child: const Text(
                      'Continue',
                      style: TextStyle(
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ),
                ),
              )
            ],
          ),
          const SizedBox(
            height: 12,
          ),
          InkWell(
            child: Text(
              'Need Help?',
              style: TextStyle(
                color: Colors.grey.shade300,
                decoration: TextDecoration.underline,
              ),
            ),
            onTap: () {
              Intercom.instance.displayMessenger();
            },
          ),
        ],
      ),
    );
  }
}
