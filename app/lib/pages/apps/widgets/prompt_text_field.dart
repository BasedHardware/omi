import 'package:flutter/material.dart';

class PromptTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final IconData icon;
  const PromptTextField({super.key, required this.controller, required this.label, required this.icon});

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      maxLines: null,
      validator: (value) {
        if (value == null || value.isEmpty) {
          return 'Please enter a valid prompt';
        }
        return null;
      },
      controller: controller,
      decoration: InputDecoration(
        border: const OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(10)),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(10)),
          borderSide: BorderSide(
            color: Colors.white,
          ),
        ),
        label: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                color: WidgetStateColor.resolveWith(
                    (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
            const SizedBox(
              width: 8,
            ),
            Text(
              label,
            ),
          ],
        ),
        alignLabelWithHint: true,
        labelStyle: const TextStyle(
          color: Colors.grey,
        ),
        floatingLabelStyle: const TextStyle(
          color: Colors.white,
        ),
      ),
    );
  }
}
