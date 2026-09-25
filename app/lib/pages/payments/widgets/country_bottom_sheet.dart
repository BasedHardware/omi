import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';

class CountryBottomSheet extends StatefulWidget {
  const CountryBottomSheet({super.key});

  @override
  State<CountryBottomSheet> createState() => _CountryBottomSheetState();
}

class _CountryBottomSheetState extends State<CountryBottomSheet> {
  final TextEditingController _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _searchController.addListener(() {
      context.read<PaymentMethodProvider>().updateSearchQuery(_searchController.text.decodeString);
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Shown inside showOmiSheet, which owns the handle, close button and insets.
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: Consumer<PaymentMethodProvider>(
        builder: (context, provider, child) {
          return Column(
            children: [
              OmiSearchField(
                placeholder: context.l10n.searchCountries,
                controller: _searchController,
                onChanged: (value) => context.read<PaymentMethodProvider>().updateSearchQuery(value),
                onCleared: () => provider.updateSearchQuery(''),
              ),
              const SizedBox(height: OmiSpacing.md),
              Expanded(
                child: provider.isLoading
                    ? const OmiLoadingState()
                    : ListView.builder(
                        itemCount: provider.filteredCountries.length,
                        itemBuilder: (context, index) {
                          final country = provider.filteredCountries[index];
                          final isSelected = provider.selectedCountryId == country['id'];

                          return ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 4),
                            title: Text(
                              (country['name'] as String).decodeString,
                              style: OmiType.body.copyWith(
                                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                              ),
                            ),
                            leading: Text(countryFlagFromCode(country['id'] as String), style: OmiType.title2),
                            trailing: isSelected ? const Icon(Icons.check, color: OmiColors.accent) : null,
                            selected: isSelected,
                            onTap: () {
                              provider.setSelectedCountryId(country['id']);
                              Navigator.pop(context);
                            },
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
