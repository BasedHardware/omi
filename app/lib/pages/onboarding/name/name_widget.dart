import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:gradient_borders/gradient_borders.dart';

class NameWidget extends StatefulWidget {
  final Function goNext;
  const NameWidget({super.key, required this.goNext});

  @override
  State<NameWidget> createState() => _NameWidgetState();
}

class _NameWidgetState extends State<NameWidget> {
  late TextEditingController nameController;
  User? user;
  bool isSaving = false;

  @override
  void initState() {
    user = FirebaseAuth.instance.currentUser;
    nameController = TextEditingController(text: user?.displayName ?? '');
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          TextFormField(
            enabled: true,
            controller: nameController,
            // textCapitalization: TextCapitalization.sentences,
            obscureText: false,
            // canRequestFocus: true,
            textAlign: TextAlign.start,
            textAlignVertical: TextAlignVertical.center,
            decoration: InputDecoration(
              hintText: 'Enter your name',
              hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
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
            style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
          ),
          const SizedBox(height: 16),
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
                        ScaffoldMessenger.of(context)
                            .showSnackBar(const SnackBar(content: Text('Please enter a valid name')));
                      } else {
                        FocusManager.instance.primaryFocus?.unfocus();
                        setState(() {
                          isSaving = true;
                        });
                        await updateFullName(nameController.text).then((value) {
                          setState(() {
                            isSaving = false;
                          });
                        });
                        widget.goNext();
                      }
                    },
                    child: isSaving
                        ? const CircularProgressIndicator(
                            color: Colors.white,
                          )
                        : const Text(
                            'Sounds good!',
                            style: TextStyle(
                              decoration: TextDecoration.none,
                            ),
                          ),
                  ),
                ),
              )
            ],
          ),
        ],
      ),
    );
  }
}
