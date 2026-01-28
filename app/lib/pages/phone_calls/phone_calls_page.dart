import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:intl_phone_field/countries.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_setup_intro_page.dart';
import 'package:omi/providers/phone_call_provider.dart';

class PhoneCallsPage extends StatefulWidget {
  const PhoneCallsPage({super.key});

  @override
  State<PhoneCallsPage> createState() => _PhoneCallsPageState();
}

class _PhoneCallsPageState extends State<PhoneCallsPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _dialpadController = TextEditingController();

  List<Contact> _contacts = [];
  List<Contact> _filteredContacts = [];
  bool _loadingContacts = true;
  bool _permissionDenied = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _loadContacts();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PhoneCallProvider>().loadVerifiedNumbers();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _searchController.dispose();
    _dialpadController.dispose();
    super.dispose();
  }

  Future<void> _loadContacts() async {
    try {
      bool hasPermission = await FlutterContacts.requestPermission(readonly: true);
      if (!hasPermission) {
        setState(() {
          _permissionDenied = true;
          _loadingContacts = false;
        });
        return;
      }

      var contacts = await FlutterContacts.getContacts(withProperties: true, withPhoto: false);
      contacts = contacts.where((c) => c.phones.isNotEmpty).toList();
      contacts.sort((a, b) => a.displayName.compareTo(b.displayName));

      setState(() {
        _contacts = contacts;
        _filteredContacts = contacts;
        _loadingContacts = false;
      });
    } catch (e) {
      setState(() {
        _loadingContacts = false;
      });
    }
  }

  void _filterContacts(String query) {
    setState(() {
      if (query.isEmpty) {
        _filteredContacts = _contacts;
      } else {
        _filteredContacts = _contacts.where((c) {
          return c.displayName.toLowerCase().contains(query.toLowerCase()) ||
              c.phones.any((p) => p.number.contains(query));
        }).toList();
      }
    });
  }

  Future<void> _makeCall(String phoneNumber, {String? contactName}) async {
    var provider = context.read<PhoneCallProvider>();

    if (provider.verifiedNumbers.isEmpty) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const PhoneSetupIntroPage()),
      );
      return;
    }

    // If the number doesn't start with '+', prepend the country code from the user's verified number
    if (!phoneNumber.startsWith('+')) {
      var verified = provider.verifiedNumbers.first.phoneNumber;
      var countryCode = _extractCountryCode(verified);
      if (countryCode != null) {
        phoneNumber = '$countryCode$phoneNumber';
      }
    }

    var messenger = ScaffoldMessenger.of(context);

    var success = await provider.startCall(phoneNumber);
    if (!mounted) return;

    if (success) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const ActiveCallPage()),
      );
    } else {
      messenger.showSnackBar(
        SnackBar(content: Text(provider.error ?? 'Failed to start call')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        title: const Text('Phone', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: Colors.white,
          indicatorWeight: 3,
          labelColor: Colors.white,
          labelStyle: const TextStyle(fontWeight: FontWeight.w600),
          unselectedLabelColor: Colors.grey[600],
          tabs: const [
            Tab(text: 'Contacts'),
            Tab(text: 'Keypad'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildContactsTab(),
          _buildKeypadTab(),
        ],
      ),
    );
  }

  Widget _buildContactsTab() {
    if (_permissionDenied) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.contacts_outlined, size: 48, color: Colors.grey[700]),
              const SizedBox(height: 16),
              Text(
                'Grant access to your contacts',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16, color: Colors.grey[400]),
              ),
              const SizedBox(height: 24),
              GestureDetector(
                onTap: () async {
                  await FlutterContacts.requestPermission(readonly: true);
                  _loadContacts();
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
                  decoration: BoxDecoration(
                    color: Colors.deepPurple,
                    borderRadius: BorderRadius.circular(28),
                  ),
                  child: const Text(
                    'Allow',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (_loadingContacts) {
      return const Center(child: CircularProgressIndicator(color: Colors.white));
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            controller: _searchController,
            onChanged: _filterContacts,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'Search',
              hintStyle: TextStyle(color: Colors.grey[600]),
              prefixIcon: Icon(Icons.search, color: Colors.grey[600]),
              filled: true,
              fillColor: const Color(0xFF1F1F25),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
        Expanded(
          child: _filteredContacts.isEmpty
              ? Center(
                  child: Text('No contacts found', style: TextStyle(color: Colors.grey[600], fontSize: 14)),
                )
              : ListView.separated(
                  itemCount: _filteredContacts.length,
                  separatorBuilder: (_, __) => Divider(color: Colors.grey[900], height: 1, indent: 72),
                  itemBuilder: (context, index) {
                    var contact = _filteredContacts[index];
                    var phone = contact.phones.first;
                    return _ContactRow(
                      name: contact.displayName,
                      phone: '${phone.label.name} ${phone.number}',
                      initial: contact.displayName.isNotEmpty ? contact.displayName[0].toUpperCase() : '?',
                      onCall: () => _makeCall(phone.number, contactName: contact.displayName),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildKeypadTab() {
    var hasDigits = _dialpadController.text.isNotEmpty;
    return Column(
      children: [
        const Spacer(flex: 2),
        // Number display — sits right above the keypad
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: SizedBox(
            height: 56,
            child: Row(
              children: [
                // Invisible spacer to balance the backspace button
                const SizedBox(width: 48),
                Expanded(
                  child: Text(
                    hasDigits ? _dialpadController.text : 'Enter number',
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: hasDigits ? (_dialpadController.text.length > 12 ? 24 : 32) : 20,
                      fontWeight: FontWeight.w300,
                      letterSpacing: hasDigits ? 2 : 0,
                      color: hasDigits ? Colors.white : Colors.grey[600],
                    ),
                  ),
                ),
                SizedBox(
                  width: 48,
                  child: hasDigits
                      ? GestureDetector(
                          onTap: () {
                            HapticFeedback.lightImpact();
                            setState(() {
                              _dialpadController.text =
                                  _dialpadController.text.substring(0, _dialpadController.text.length - 1);
                            });
                          },
                          onLongPress: () {
                            HapticFeedback.mediumImpact();
                            setState(() {
                              _dialpadController.text = '';
                            });
                          },
                          child: Icon(Icons.backspace_outlined, color: Colors.grey[500], size: 22),
                        )
                      : null,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Keypad grid
        _buildDialpad(),
        const SizedBox(height: 20),
        // Call button
        GestureDetector(
          onTap: hasDigits
              ? () {
                  HapticFeedback.mediumImpact();
                  _makeCall(_dialpadController.text);
                }
              : null,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 68,
            height: 68,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: hasDigits ? Colors.green : const Color(0xFF1F1F25),
            ),
            child: Icon(
              Icons.phone,
              color: hasDigits ? Colors.white : Colors.grey[600],
              size: 32,
            ),
          ),
        ),
        const Spacer(flex: 1),
        SizedBox(height: MediaQuery.of(context).viewPadding.bottom + 8),
      ],
    );
  }

  Widget _buildDialpad() {
    const keys = [
      ['1', '2', '3'],
      ['4', '5', '6'],
      ['7', '8', '9'],
      ['*', '0', '#'],
    ];
    const subtexts = [
      ['', 'ABC', 'DEF'],
      ['GHI', 'JKL', 'MNO'],
      ['PQRS', 'TUV', 'WXYZ'],
      ['', '+', ''],
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(keys.length, (row) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: List.generate(keys[row].length, (col) {
                return _DialpadKey(
                  digit: keys[row][col],
                  subtext: subtexts[row][col],
                  onTap: () {
                    HapticFeedback.lightImpact();
                    setState(() {
                      _dialpadController.text += keys[row][col];
                    });
                  },
                  onLongPress: keys[row][col] == '0'
                      ? () {
                          HapticFeedback.mediumImpact();
                          setState(() {
                            _dialpadController.text += '+';
                          });
                        }
                      : null,
                );
              }),
            ),
          );
        }),
      ),
    );
  }

  /// Extracts the country code (e.g. "+1", "+91") from an E.164 phone number
  /// by matching against known country dial codes (longest match first).
  String? _extractCountryCode(String e164Number) {
    if (!e164Number.startsWith('+')) return null;
    var digits = e164Number.substring(1); // strip '+'
    // Try longest match first (country codes are 1-3 digits)
    for (var len = 3; len >= 1; len--) {
      if (digits.length <= len) continue;
      var candidate = digits.substring(0, len);
      if (countries.any((c) => c.fullCountryCode == candidate)) {
        return '+$candidate';
      }
    }
    return null;
  }
}

class _ContactRow extends StatelessWidget {
  final String name;
  final String phone;
  final String initial;
  final VoidCallback onCall;

  const _ContactRow({
    required this.name,
    required this.phone,
    required this.initial,
    required this.onCall,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onCall,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 20,
              backgroundColor: Colors.grey[800],
              child: Text(initial, style: const TextStyle(color: Colors.white, fontSize: 16)),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontSize: 16, color: Colors.white)),
                  const SizedBox(height: 2),
                  Text(phone, style: TextStyle(fontSize: 13, color: Colors.grey[500])),
                ],
              ),
            ),
            GestureDetector(
              onTap: onCall,
              child: Icon(Icons.phone, color: Colors.grey[400], size: 22),
            ),
          ],
        ),
      ),
    );
  }
}

class _DialpadKey extends StatelessWidget {
  final String digit;
  final String subtext;
  final VoidCallback onTap;
  final VoidCallback? onLongPress;

  const _DialpadKey({
    required this.digit,
    required this.subtext,
    required this.onTap,
    this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      onLongPress: onLongPress,
      borderRadius: BorderRadius.circular(36),
      splashColor: Colors.white.withValues(alpha: 0.08),
      highlightColor: Colors.white.withValues(alpha: 0.05),
      child: Container(
        width: 72,
        height: 72,
        decoration: const BoxDecoration(
          shape: BoxShape.circle,
          color: Color(0xFF1F1F25),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(digit, style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w300, color: Colors.white)),
            if (subtext.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Text(
                  subtext,
                  style:
                      TextStyle(fontSize: 10, fontWeight: FontWeight.w500, color: Colors.grey[600], letterSpacing: 1.5),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
