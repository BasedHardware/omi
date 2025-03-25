import 'package:flutter/material.dart';

class CustomBackendURLForm extends StatefulWidget {
  const CustomBackendURLForm({super.key});

  @override
  State<StatefulWidget> createState() => _CustomBackendURLFormState();
}

class _CustomBackendURLFormState extends State<CustomBackendURLForm> {
  final _formKey = GlobalKey<FormState>();
  final _urlController = TextEditingController();

  // Function to validate the URL
  String? _validateURL(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter the backend URL';
    }

    // Check if the URL ends with '/'
    if (!value.endsWith('/')) {
      return 'URL must end with "/"';
    }

    // Use Uri.tryParse to validate the URL format
    final Uri? uri = Uri.tryParse(value);
    if (uri == null || !uri.hasAbsolutePath || uri.scheme.isEmpty) {
      return 'Please enter a valid URL';
    }

    return null;
  }

  void _submitForm() {
    if (_formKey.currentState!.validate()) {
      // Form is valid, proceed further
      String backendURL = _urlController.text;

      // Print or save the backend URL as needed
      print('Custom Backend URL: $backendURL');

      // Show a success message
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Backend URL saved successfully!')),
      );
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // For consistent styling, you can reuse the theme from the previous form
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
                        'Custom Backend URL',
                        style: TextStyle(
                          fontSize: 28.0,
                          fontWeight: FontWeight.bold,
                          color: Colors.blueAccent[700],
                        ),
                      ),
                      const SizedBox(height: 20),
                      TextFormField(
                        controller: _urlController,
                        decoration: InputDecoration(
                          labelText: 'Backend URL',
                          prefixIcon: const Icon(Icons.link),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                        validator: _validateURL,
                        keyboardType: TextInputType.url,
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
                          child: const Text(
                            'Save URL',
                            style: TextStyle(fontSize: 18.0),
                          ),
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
