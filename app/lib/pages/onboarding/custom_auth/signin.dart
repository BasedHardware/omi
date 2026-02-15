import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

class CustomAuthSignUp extends StatefulWidget {
  const CustomAuthSignUp({super.key});

  @override
  State<StatefulWidget> createState() => CustomAuthSignUpState();
}

class CustomAuthSignUpState extends State<CustomAuthSignUp> {
  final _formKey = GlobalKey<FormState>();

  // Controllers for the text fields
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  // Function to validate email
  String? _validateEmail(String? value, BuildContext context) {
    if (value == null || value.isEmpty) {
      return context.l10n.enterEmailError;
    }
    final RegExp emailRegex = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
    if (!emailRegex.hasMatch(value)) {
      return context.l10n.invalidEmailError;
    }
    return null;
  }

  // Function to validate password
  String? _validatePassword(String? value, BuildContext context) {
    if (value == null || value.isEmpty) {
      return context.l10n.enterPasswordError;
    }
    if (value.length < 8) {
      return context.l10n.passwordMinLengthError;
    }
    return null;
  }

  void _submitForm() {
    if (_formKey.currentState!.validate()) {
      // Form is valid, proceed further
      Map<String, String> formData = {
        'email': _emailController.text,
        'password': _passwordController.text,
      };

      String jsonString = jsonEncode(formData);
      print(jsonString);

      // You can show a success message or navigate to another page here
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.signInSuccess)),
      );
    }
  }

  @override
  void dispose() {
    // Dispose of the controllers when the widget is disposed
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Define a custom theme
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          // Add gradient background
          gradient: LinearGradient(
            colors: [Color(0xFF6A11CB), Color(0xFF2575FC)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24.0),
            child: Card(
              elevation: 8.0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16.0),
              ),
              margin: const EdgeInsets.symmetric(vertical: 24.0),
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        context.l10n.signInTitle,
                        style: TextStyle(
                          fontSize: 28.0,
                          fontWeight: FontWeight.bold,
                          color: Colors.blueAccent[700],
                        ),
                      ),
                      const SizedBox(height: 20),
                      TextFormField(
                        controller: _emailController,
                        decoration: InputDecoration(
                          labelText: context.l10n.emailLabel,
                          prefixIcon: const Icon(Icons.email),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                        validator: (value) => _validateEmail(value, context),
                        keyboardType: TextInputType.emailAddress,
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: _passwordController,
                        decoration: InputDecoration(
                          labelText: context.l10n.passwordLabel,
                          prefixIcon: const Icon(Icons.lock),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                        obscureText: true,
                        validator: (value) => _validatePassword(value, context),
                      ),
                      const SizedBox(height: 24),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton(
                          onPressed: _submitForm,
                          style: ElevatedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 16.0),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12.0),
                            ),
                            backgroundColor: Colors.blueAccent[700],
                          ),
                          child: Text(
                            context.l10n.signInButton,
                            style: const TextStyle(fontSize: 18.0),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      TextButton(
                        onPressed: () {
                          // Navigate to login page
                        },
                        child: Text(
                          context.l10n.alreadyHaveAccountLogin,
                          style: const TextStyle(color: Colors.grey),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
