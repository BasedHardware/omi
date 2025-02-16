import 'dart:io';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

class AddPersonaPage extends StatefulWidget {
  const AddPersonaPage({super.key});

  @override
  State<AddPersonaPage> createState() => _AddPersonaPageState();
}

class _AddPersonaPageState extends State<AddPersonaPage> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  bool _isPublic = false;
  File? _selectedImage;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _nameController.text = SharedPreferencesUtil().givenName;
    _emailController.text = SharedPreferencesUtil().email;
  }

  Future<void> _pickImage() async {
    final ImagePicker picker = ImagePicker();
    final XFile? image = await picker.pickImage(source: ImageSource.gallery);
    if (image != null) {
      setState(() {
        _selectedImage = File(image.path);
      });
    }
  }

  Future<void> _createPersona() async {
    if (!_formKey.currentState!.validate() || _selectedImage == null) {
      if (_selectedImage == null) {
        AppSnackbar.showSnackbarError('Please select an image');
      }
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final personaData = {
        'author': _nameController.text,
        'private': !_isPublic,
      };

      var res = await createPersonaApp(_selectedImage!, personaData);

      if (mounted) {
        if (res) {
          context.read<AppProvider>().getApps();
          AppSnackbar.showSnackbarSuccess('Persona created successfully');
        } else {
          AppSnackbar.showSnackbarError('Failed to create your persona');
        }
      }
    } catch (e) {
      if (mounted) {
        AppSnackbar.showSnackbarError('Failed to create persona: $e');
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        title: const Text('Create Persona', style: TextStyle(color: Colors.white)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: GestureDetector(
                    onTap: _pickImage,
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(60),
                        border: Border.all(color: Colors.grey.shade800),
                      ),
                      child: _selectedImage != null
                          ? ClipRRect(
                              borderRadius: BorderRadius.circular(60),
                              child: Image.file(
                                _selectedImage!,
                                fit: BoxFit.cover,
                              ),
                            )
                          : Icon(
                              Icons.add_a_photo,
                              size: 40,
                              color: Colors.grey.shade400,
                            ),
                    ),
                  ),
                ),
                const SizedBox(height: 32),
                TextFormField(
                  controller: _nameController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Name',
                    labelStyle: TextStyle(color: Colors.grey.shade400),
                    enabledBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: Colors.grey.shade800),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: Colors.grey.shade600),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please enter a name';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Text(
                      'Make Persona Public',
                      style: TextStyle(color: Colors.grey.shade400),
                    ),
                    const Spacer(),
                    Switch(
                      value: _isPublic,
                      onChanged: (value) {
                        setState(() {
                          _isPublic = value;
                        });
                      },
                      activeColor: Colors.white,
                    ),
                  ],
                ),
                const SizedBox(height: 32),
              ],
            ),
          ),
        ),
      ),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.only(left: 24, right: 24, bottom: 52),
        child: SizedBox(
          width: double.infinity,
          child: AnimatedLoadingButton(
            onPressed: _createPersona,
            color: Colors.white,
            loaderColor: Colors.black,
            text: "Create Persona",
            textStyle: const TextStyle(
              color: Colors.black,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}
