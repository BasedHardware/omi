import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl_phone_field/countries.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/phone_setup_verify_page.dart';
import 'package:omi/providers/phone_call_provider.dart';

class PhoneSetupNumberPage extends StatefulWidget {
  const PhoneSetupNumberPage({super.key});

  @override
  State<PhoneSetupNumberPage> createState() => _PhoneSetupNumberPageState();
}

class _PhoneSetupNumberPageState extends State<PhoneSetupNumberPage> {
  final TextEditingController _phoneController = TextEditingController();
  final FocusNode _phoneFocus = FocusNode();
  Country _selectedCountry = countries.firstWhere((c) => c.code == 'US');
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _phoneFocus.requestFocus();
    });
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _phoneFocus.dispose();
    super.dispose();
  }

  bool get _isValid {
    var digits = _phoneController.text.replaceAll(RegExp(r'\D'), '');
    return digits.length >= _selectedCountry.minLength && digits.length <= _selectedCountry.maxLength;
  }

  String get _fullNumber {
    var digits = _phoneController.text.replaceAll(RegExp(r'\D'), '');
    return '+${_selectedCountry.fullCountryCode}$digits';
  }

  void _showCountryPicker() {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      isScrollControlled: true,
      builder: (_) => _CountryPickerSheet(
        selected: _selectedCountry,
        onSelect: (country) {
          setState(() => _selectedCountry = country);
          Navigator.pop(context);
          _phoneFocus.requestFocus();
        },
      ),
    );
  }

  Future<void> _onContinue() async {
    if (!_isValid) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    var provider = context.read<PhoneCallProvider>();
    var success = await provider.startVerification(_fullNumber);

    if (!mounted) return;

    if (success) {
      if (provider.verificationStatus == 'verified') {
        await provider.loadVerifiedNumbers();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const _AlreadyVerifiedRedirect()),
          (route) => route.isFirst,
        );
        return;
      }

      setState(() => _isLoading = false);
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => PhoneSetupVerifyPage(
            phoneNumber: _fullNumber,
            validationCode: provider.validationCode,
          ),
        ),
      );
    } else {
      setState(() {
        _isLoading = false;
        _errorMessage = provider.error ?? 'Failed to start verification';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: 60),
              const Text(
                'Enter your number',
                style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Colors.white),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Once verified, this becomes your caller ID',
                style: TextStyle(fontSize: 15, color: Colors.grey[500]),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    GestureDetector(
                      onTap: _showCountryPicker,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(_selectedCountry.flag, style: const TextStyle(fontSize: 22)),
                            const SizedBox(width: 6),
                            Text(
                              '+${_selectedCountry.fullCountryCode}',
                              style: const TextStyle(color: Colors.white, fontSize: 16),
                            ),
                            const SizedBox(width: 4),
                            Icon(Icons.arrow_drop_down, color: Colors.grey[500], size: 20),
                          ],
                        ),
                      ),
                    ),
                    Container(width: 1, height: 28, color: Colors.grey[800]),
                    Expanded(
                      child: TextField(
                        controller: _phoneController,
                        focusNode: _phoneFocus,
                        keyboardType: TextInputType.phone,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                          hintText: 'Phone number',
                          hintStyle: TextStyle(color: Colors.grey[600]),
                        ),
                        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9\s\-\(\)]'))],
                        onChanged: (_) => setState(() => _errorMessage = null),
                      ),
                    ),
                  ],
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 12),
                Text(
                  _errorMessage!,
                  style: TextStyle(fontSize: 13, color: Colors.red[400]),
                  textAlign: TextAlign.center,
                ),
              ],
              const Spacer(),
              GestureDetector(
                onTap: (_isValid && !_isLoading)
                    ? () {
                        HapticFeedback.mediumImpact();
                        _onContinue();
                      }
                    : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: double.infinity,
                  height: 56,
                  decoration: BoxDecoration(
                    color: (_isValid && !_isLoading) ? Colors.deepPurple : Colors.grey[800],
                    borderRadius: BorderRadius.circular(28),
                  ),
                  alignment: Alignment.center,
                  child: _isLoading
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Text(
                          'Continue',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
                        ),
                ),
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _CountryPickerSheet extends StatefulWidget {
  final Country selected;
  final ValueChanged<Country> onSelect;

  const _CountryPickerSheet({required this.selected, required this.onSelect});

  @override
  State<_CountryPickerSheet> createState() => _CountryPickerSheetState();
}

class _CountryPickerSheetState extends State<_CountryPickerSheet> {
  final TextEditingController _searchController = TextEditingController();
  List<Country> _filtered = countries;

  void _filter(String query) {
    var q = query.toLowerCase();
    setState(() {
      _filtered = countries.where((c) {
        return c.name.toLowerCase().contains(q) || c.dialCode.contains(q) || c.code.toLowerCase().contains(q);
      }).toList();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.4,
      maxChildSize: 0.9,
      expand: false,
      builder: (_, scrollController) => Column(
        children: [
          const SizedBox(height: 12),
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              controller: _searchController,
              onChanged: _filter,
              style: const TextStyle(color: Colors.white, fontSize: 15),
              decoration: InputDecoration(
                filled: true,
                fillColor: const Color(0xFF1F1F25),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                prefixIcon: Icon(Icons.search, color: Colors.grey[600], size: 20),
                hintText: 'Search countries',
                hintStyle: TextStyle(color: Colors.grey[600], fontSize: 15),
                contentPadding: const EdgeInsets.symmetric(vertical: 12),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: ListView.builder(
              controller: scrollController,
              itemCount: _filtered.length,
              itemBuilder: (_, i) {
                var c = _filtered[i];
                var isSelected = c.code == widget.selected.code;
                return GestureDetector(
                  onTap: () => widget.onSelect(c),
                  child: Container(
                    color: Colors.transparent,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    child: Row(
                      children: [
                        Text(c.flag, style: const TextStyle(fontSize: 22)),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            c.name,
                            style: TextStyle(
                              fontSize: 15,
                              color: isSelected ? Colors.white : Colors.grey[300],
                              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        Text(
                          '+${c.fullCountryCode}',
                          style: TextStyle(fontSize: 14, color: Colors.grey[500]),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _AlreadyVerifiedRedirect extends StatelessWidget {
  const _AlreadyVerifiedRedirect();

  @override
  Widget build(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Navigator.of(context).pop();
    });
    return const Scaffold(backgroundColor: Colors.black);
  }
}
