import 'package:flutter/material.dart';

class PromptTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  const PromptTextField({super.key, required this.controller, required this.label, required this.hint});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 8.0),
          child: Text(
            label,
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
                  maxLines: null,
                  controller: controller,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please provide a prompt';
                    }
                    return null;
                  },
                  decoration: InputDecoration(
                    contentPadding: const EdgeInsets.only(top: 6, bottom: 2),
                    isDense: true,
                    errorText: null,
                    border: InputBorder.none,
                    hintText: hint,
                    hintMaxLines: 4,
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
