import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:url_launcher/url_launcher.dart';

/// Contact with phone number for sharing
class ShareableContact {
  final String id;
  final String displayName;
  final String phoneNumber;
  bool isSelected;

  ShareableContact({
    required this.id,
    required this.displayName,
    required this.phoneNumber,
    this.isSelected = false,
  });
}

/// Show the share to contacts bottom sheet
void showShareToContactsBottomSheet(BuildContext context, ServerConversation conversation) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => ShareToContactsBottomSheet(conversation: conversation),
  );
}

/// Bottom sheet for selecting contacts and sharing conversation via native SMS
class ShareToContactsBottomSheet extends StatefulWidget {
  final ServerConversation conversation;

  const ShareToContactsBottomSheet({super.key, required this.conversation});

  @override
  State<ShareToContactsBottomSheet> createState() => _ShareToContactsBottomSheetState();
}

class _ShareToContactsBottomSheetState extends State<ShareToContactsBottomSheet> {
  final TextEditingController _searchController = TextEditingController();
  List<ShareableContact> _contacts = [];
  List<ShareableContact> _filteredContacts = [];
  bool _isLoading = true;
  bool _isPreparingShare = false;
  String? _errorMessage;
  bool _permissionDenied = false;

  @override
  void initState() {
    super.initState();
    // Track sheet opened
    MixpanelManager().shareToContactsSheetOpened(widget.conversation.id);
    _loadContacts();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadContacts() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _permissionDenied = false;
    });

    // Request contacts permission using flutter_contacts' own method
    final permissionGranted = await FlutterContacts.requestPermission();

    if (!permissionGranted) {
      setState(() {
        _isLoading = false;
        _permissionDenied = true;
        _errorMessage = 'Contacts permission is required to share via SMS';
      });
      return;
    }

    try {
      // Fetch contacts with phone numbers
      final contacts = await FlutterContacts.getContacts(
        withProperties: true,
        withPhoto: false,
      );

      // Filter contacts that have phone numbers and create ShareableContact list
      final shareableContacts = <ShareableContact>[];
      for (final contact in contacts) {
        for (final phone in contact.phones) {
          if (phone.number.isNotEmpty) {
            shareableContacts.add(ShareableContact(
              id: '${contact.id}_${phone.number}',
              displayName: contact.displayName.isNotEmpty ? contact.displayName : phone.number,
              phoneNumber: _cleanPhoneNumber(phone.number),
            ));
          }
        }
      }

      // Sort by display name
      shareableContacts.sort((a, b) => a.displayName.toLowerCase().compareTo(b.displayName.toLowerCase()));

      setState(() {
        _contacts = shareableContacts;
        _filteredContacts = shareableContacts;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Failed to load contacts: $e';
      });
    }
  }

  /// Clean phone number for SMS URI (remove spaces, dashes, etc.)
  String _cleanPhoneNumber(String phone) {
    return phone.replaceAll(RegExp(r'[\s\-\(\)]'), '');
  }

  void _filterContacts(String query) {
    if (query.isEmpty) {
      setState(() {
        _filteredContacts = _contacts;
      });
      return;
    }

    final lowerQuery = query.toLowerCase();
    setState(() {
      _filteredContacts = _contacts.where((contact) {
        return contact.displayName.toLowerCase().contains(lowerQuery) || contact.phoneNumber.contains(query);
      }).toList();
    });
  }

  void _toggleContactSelection(ShareableContact contact) {
    setState(() {
      contact.isSelected = !contact.isSelected;
    });
    // Track selection changes
    final selectedCount = _selectedContacts.length;
    if (selectedCount > 0) {
      MixpanelManager().shareToContactsSelected(widget.conversation.id, selectedCount);
    }
  }

  List<ShareableContact> get _selectedContacts => _contacts.where((c) => c.isSelected).toList();

  Future<void> _openNativeSms() async {
    final selected = _selectedContacts;
    if (selected.isEmpty) return;

    setState(() {
      _isPreparingShare = true;
      _errorMessage = null;
    });

    try {
      // First, set conversation to shared visibility
      final shared = await setConversationVisibility(widget.conversation.id);
      if (!shared) {
        if (!mounted) return;
        setState(() {
          _isPreparingShare = false;
          _errorMessage = 'Failed to prepare conversation for sharing. Please try again.';
        });
        return;
      }

      // Build the share link and message
      final shareLink = 'https://h.omi.me/conversations/${widget.conversation.id}';
      final message = "Here's what we just discussed: $shareLink";

      // Build recipients string (comma-separated phone numbers)
      final recipients = selected.map((c) => c.phoneNumber).join(',');

      // Build SMS URI
      // iOS uses & for body separator, Android uses ?
      final Uri smsUri;
      if (Platform.isIOS) {
        smsUri = Uri.parse('sms:$recipients&body=${Uri.encodeComponent(message)}');
      } else {
        smsUri = Uri.parse('sms:$recipients?body=${Uri.encodeComponent(message)}');
      }

      if (!mounted) return;

      // Launch native SMS app
      if (await canLaunchUrl(smsUri)) {
        // Track SMS opened
        MixpanelManager().shareToContactsSmsOpened(widget.conversation.id, selected.length);
        HapticFeedback.mediumImpact();
        Navigator.of(context).pop();
        await launchUrl(smsUri);
      } else {
        setState(() {
          _isPreparingShare = false;
          _errorMessage = 'Could not open SMS app. Please try again.';
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isPreparingShare = false;
        _errorMessage = 'Error: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1A1A1A),
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
          ),
          child: Column(
            children: [
              // Handle bar
              Container(
                margin: const EdgeInsets.only(top: 12),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade600,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              // Header
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Share via SMS',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, color: Colors.grey),
                          onPressed: () => Navigator.of(context).pop(),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Select contacts to share your conversation summary',
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey.shade400,
                      ),
                    ),
                  ],
                ),
              ),
              // Search bar
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TextField(
                  controller: _searchController,
                  onChanged: _filterContacts,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: 'Search contacts...',
                    hintStyle: TextStyle(color: Colors.grey.shade500),
                    prefixIcon: const Icon(Icons.search, color: Colors.grey),
                    filled: true,
                    fillColor: const Color(0xFF2A2A2A),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              // Selected count
              if (_selectedContacts.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.deepPurple.withOpacity(0.3),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          '${_selectedContacts.length} selected',
                          style: const TextStyle(
                            color: Colors.deepPurple,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () {
                          setState(() {
                            for (var contact in _contacts) {
                              contact.isSelected = false;
                            }
                          });
                        },
                        child: const Text(
                          'Clear all',
                          style: TextStyle(color: Colors.grey),
                        ),
                      ),
                    ],
                  ),
                ),
              // Error message
              if (_errorMessage != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.red.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline, color: Colors.red, size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _errorMessage!,
                            style: const TextStyle(color: Colors.red, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              // Contacts list
              Expanded(
                child: _buildContactsList(scrollController),
              ),
              // Send button
              if (!_permissionDenied)
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _selectedContacts.isEmpty || _isPreparingShare ? null : _openNativeSms,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.deepPurple,
                          disabledBackgroundColor: Colors.grey.shade800,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: _isPreparingShare
                            ? const SizedBox(
                                width: 24,
                                height: 24,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              )
                            : Text(
                                _selectedContacts.isEmpty
                                    ? 'Select contacts to share'
                                    : 'Share with ${_selectedContacts.length} contact${_selectedContacts.length > 1 ? 's' : ''}',
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: Colors.white,
                                ),
                              ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildContactsList(ScrollController scrollController) {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.deepPurple),
      );
    }

    if (_permissionDenied) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.contacts, size: 64, color: Colors.grey.shade600),
            const SizedBox(height: 16),
            Text(
              'Contacts permission required',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Colors.grey.shade400,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Please grant contacts permission to share via SMS',
              style: TextStyle(color: Colors.grey.shade500),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () async {
                // Open app settings
                if (Platform.isIOS) {
                  await launchUrl(Uri.parse('app-settings:'));
                } else {
                  await launchUrl(Uri.parse('package:com.friend.ios'));
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
              ),
              child: const Text('Open Settings'),
            ),
          ],
        ),
      );
    }

    if (_filteredContacts.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.search_off, size: 64, color: Colors.grey.shade600),
            const SizedBox(height: 16),
            Text(
              _searchController.text.isEmpty ? 'No contacts with phone numbers found' : 'No contacts match your search',
              style: TextStyle(
                fontSize: 16,
                color: Colors.grey.shade400,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      itemCount: _filteredContacts.length,
      itemBuilder: (context, index) {
        final contact = _filteredContacts[index];
        return _buildContactTile(contact);
      },
    );
  }

  Widget _buildContactTile(ShareableContact contact) {
    return ListTile(
      onTap: () => _toggleContactSelection(contact),
      leading: CircleAvatar(
        backgroundColor: contact.isSelected ? Colors.deepPurple : Colors.grey.shade800,
        child: contact.isSelected
            ? const Icon(Icons.check, color: Colors.white, size: 20)
            : Text(
                contact.displayName.isNotEmpty ? contact.displayName[0].toUpperCase() : '?',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
              ),
      ),
      title: Text(
        contact.displayName,
        style: TextStyle(
          color: Colors.white,
          fontWeight: contact.isSelected ? FontWeight.w600 : FontWeight.normal,
        ),
      ),
      subtitle: Text(
        contact.phoneNumber,
        style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
      ),
      trailing: contact.isSelected
          ? const Icon(Icons.check_circle, color: Colors.deepPurple)
          : Icon(Icons.circle_outlined, color: Colors.grey.shade600),
    );
  }
}
