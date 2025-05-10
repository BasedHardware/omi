import 'package:flutter/material.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

import '../payment_method_provider.dart';

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
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.5,
      maxChildSize: 0.9,
      expand: false,
      builder: (context, scrollController) {
        return Consumer<PaymentMethodProvider>(builder: (context, provider, child) {
          return Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Column(
              children: [
                Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.symmetric(vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.grey[600],
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                TextField(
                  controller: _searchController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: 'Search countries...',
                    hintStyle: TextStyle(color: Colors.grey[400]),
                    filled: true,
                    fillColor: Colors.white.withOpacity(0.1),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide.none,
                    ),
                    prefixIcon: const Icon(Icons.search, color: Colors.white),
                    suffixIcon: provider.searchQuery.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, color: Colors.white),
                            onPressed: () {
                              _searchController.clear();
                              provider.updateSearchQuery('');
                            },
                          )
                        : null,
                  ),
                  onChanged: (value) {
                    context.read<PaymentMethodProvider>().updateSearchQuery(value);
                  },
                ),
                const SizedBox(height: 16),
                Expanded(
                  child: Builder(
                    builder: (context) {
                      if (provider.isLoading) {
                        return const Center(
                          child: CircularProgressIndicator(color: Color(0xFF635BFF)),
                        );
                      }

                      return ListView.builder(
                        controller: scrollController,
                        itemCount: provider.filteredCountries.length,
                        itemBuilder: (context, index) {
                          final country = provider.filteredCountries[index];
                          final isSelected = provider.selectedCountryId == country['id'];

                          return ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            title: Text(
                              (country['name'] as String).decodeString,
                              style: TextStyle(
                                color: isSelected ? const Color(0xFF635BFF) : Colors.white,
                                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                              ),
                            ),
                            leading: Text(
                              countryFlagFromCode(country['id'] as String),
                              style: const TextStyle(fontSize: 24),
                            ),
                            selected: isSelected,
                            onTap: () {
                              provider.setSelectedCountryId(country['id']);
                              Navigator.pop(context);
                            },
                          );
                        },
                      );
                    },
                  ),
                ),
              ],
            ),
          );
        });
      },
    );
  }
}
