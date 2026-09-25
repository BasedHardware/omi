import 'package:flutter/material.dart';
import 'package:intl_country_data/intl_country_data.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/phone_setup_verify_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/phone_number_input.dart';

class PhoneSetupNumberPage extends StatefulWidget {
  const PhoneSetupNumberPage({super.key});

  @override
  State<PhoneSetupNumberPage> createState() => _PhoneSetupNumberPageState();
}

class _PhoneSetupNumberPageState extends State<PhoneSetupNumberPage> {
  final TextEditingController _phoneController = TextEditingController();
  final FocusNode _phoneFocus = FocusNode();
  IntlCountryData _selectedCountry = IntlCountryData.fromCountryCodeAlpha2('US');
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

  PhoneNumberInput get _parsed => parsePhoneNumberInput(
        raw: _phoneController.text,
        isoCode: _selectedCountry.codeAlpha2,
      );

  bool get _isValid => _parsed.isValid;

  String get _fullNumber => _parsed.e164;

  void _showCountryPicker() {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.phoneSelectCountryTitle,
      padding: EdgeInsets.zero,
      builder: (sheetContext) => _CountryPickerSheet(
        selected: _selectedCountry,
        onSelect: (country) {
          setState(() => _selectedCountry = country);
          Navigator.pop(sheetContext);
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
          omiPageRoute(builder: (_) => const _AlreadyVerifiedRedirect()),
          (route) => route.isFirst,
        );
        return;
      }

      setState(() => _isLoading = false);
      routeToPage(
        context,
        PhoneSetupVerifyPage(phoneNumber: _fullNumber, validationCode: provider.validationCode),
      );
    } else {
      setState(() {
        _isLoading = false;
        _errorMessage = provider.error ?? context.l10n.failedToStartVerification;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: 60),
              Semantics(
                header: true,
                child: Text(context.l10n.enterYourNumber, style: OmiType.title1, textAlign: TextAlign.center),
              ),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                context.l10n.phoneNumberCallerIdHint,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              Container(
                decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                child: Row(
                  children: [
                    Semantics(
                      button: true,
                      label: context.l10n.phoneSelectCountryTitle,
                      value: '${_selectedCountry.name} +${_selectedCountry.telephoneCode}',
                      excludeSemantics: true,
                      child: InkWell(
                        onTap: _showCountryPicker,
                        borderRadius: const BorderRadius.horizontal(left: Radius.circular(OmiRadius.lg)),
                        child: Padding(
                          padding: const EdgeInsets.all(OmiSpacing.md),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(_selectedCountry.flag, style: OmiType.title3),
                              const SizedBox(width: 6),
                              Text('+${_selectedCountry.telephoneCode}', style: OmiType.callout),
                              const SizedBox(width: OmiSpacing.xxs),
                              const Icon(Icons.arrow_drop_down, color: OmiColors.textTertiary, size: 20),
                            ],
                          ),
                        ),
                      ),
                    ),
                    Container(width: 1, height: 28, color: OmiColors.border),
                    Expanded(
                      child: TextField(
                        controller: _phoneController,
                        focusNode: _phoneFocus,
                        keyboardType: TextInputType.phone,
                        style: OmiType.callout,
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                          hintText: context.l10n.phoneNumberHint,
                          hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                        ),
                        inputFormatters: phoneFieldInputFormatters,
                        onChanged: (_) => setState(() => _errorMessage = null),
                      ),
                    ),
                  ],
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: OmiSpacing.sm),
                Semantics(
                  liveRegion: true,
                  child: Text(
                    _errorMessage!,
                    style: OmiType.footnote.copyWith(color: OmiColors.danger),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
              const Spacer(),
              OmiButton(
                label: context.l10n.phoneContinue,
                expand: true,
                isLoading: _isLoading,
                onPressed: (_isValid && !_isLoading)
                    ? () {
                        OmiHaptics.medium();
                        _onContinue();
                      }
                    : null,
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
  final IntlCountryData selected;
  final ValueChanged<IntlCountryData> onSelect;

  const _CountryPickerSheet({required this.selected, required this.onSelect});

  @override
  State<_CountryPickerSheet> createState() => _CountryPickerSheetState();
}

class _CountryPickerSheetState extends State<_CountryPickerSheet> {
  final TextEditingController _searchController = TextEditingController();
  final List<IntlCountryData> _allCountries = IntlCountryData.all();
  List<IntlCountryData> _filtered = IntlCountryData.all();

  void _filter(String query) {
    var q = query.toLowerCase();
    setState(() {
      _filtered = _allCountries.where((c) {
        return c.name.toLowerCase().contains(q) ||
            c.telephoneCode.contains(q) ||
            c.codeAlpha2.toLowerCase().contains(q);
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
    // The sheet clamps this to the space left above the keyboard.
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: OmiSearchField(
              placeholder: context.l10n.searchCountries,
              controller: _searchController,
              onChanged: _filter,
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Expanded(
            child: ListView.builder(
              itemCount: _filtered.length,
              itemBuilder: (_, i) {
                var c = _filtered[i];
                var isSelected = c.codeAlpha2 == widget.selected.codeAlpha2;
                return Semantics(
                  selected: isSelected,
                  button: true,
                  child: InkWell(
                    onTap: () => widget.onSelect(c),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
                      child: Row(
                        children: [
                          ExcludeSemantics(child: Text(c.flag, style: OmiType.title3)),
                          const SizedBox(width: OmiSpacing.sm),
                          Expanded(
                            child: Text(
                              c.name,
                              style: OmiType.subhead.copyWith(
                                color: isSelected ? OmiColors.textPrimary : OmiColors.textSecondary,
                                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            '+${c.telephoneCode}',
                            style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                          ),
                          if (isSelected) ...[
                            const SizedBox(width: OmiSpacing.xs),
                            const Icon(Icons.check, color: OmiColors.textPrimary, size: 20),
                          ],
                        ],
                      ),
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
    return const Scaffold();
  }
}
