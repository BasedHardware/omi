import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/ui/ui.dart';

/// Contact with phone number for sharing
class ShareableContact {
  final String id;
  final String displayName;
  final String phoneNumber;
  bool isSelected;

  ShareableContact({required this.id, required this.displayName, required this.phoneNumber, this.isSelected = false});
}

/// Show the share to contacts bottom sheet
void showShareToContactsBottomSheet(BuildContext context, ServerConversation conversation) {
  showOmiSheet<void>(
    context: context,
    title: context.l10n.shareViaSms,
    padding: EdgeInsets.zero,
    builder: (_) => ShareToContactsBottomSheet(conversation: conversation),
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
    PlatformManager.instance.analytics.shareToContactsSheetOpened(widget.conversation.id);
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
    final status = await FlutterContacts.permissions.request(PermissionType.readWrite);
    final permissionGranted = status == PermissionStatus.granted || status == PermissionStatus.limited;

    if (!permissionGranted) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _permissionDenied = true;
        _errorMessage = context.l10n.contactsPermissionRequiredForSms;
      });
      return;
    }

    try {
      // Fetch contacts with phone numbers
      final contacts = await FlutterContacts.getAll(properties: {ContactProperty.phone});

      // Filter contacts that have phone numbers and create ShareableContact list
      final shareableContacts = <ShareableContact>[];
      for (final contact in contacts) {
        for (final phone in contact.phones) {
          if (phone.number.isNotEmpty) {
            final displayName = contact.displayName;
            shareableContacts.add(
              ShareableContact(
                id: '${contact.id}_${phone.number}',
                displayName: displayName != null && displayName.isNotEmpty ? displayName : phone.number,
                phoneNumber: _cleanPhoneNumber(phone.number),
              ),
            );
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
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = '${context.l10n.failedToLoadContacts}: $e';
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
      PlatformManager.instance.analytics.shareToContactsSelected(widget.conversation.id, selectedCount);
    }
  }

  List<ShareableContact> get _selectedContacts => _contacts.where((c) => c.isSelected).toList();

  Future<void> _openNativeSms() async {
    final selected = _selectedContacts;
    if (selected.isEmpty) return;

    final l10n = context.l10n;
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
          _errorMessage = l10n.failedToPrepareConversationForSharing;
        });
        return;
      }
      if (mounted) {
        context.read<ConversationDetailProvider>().updateVisibilityLocally(ConversationVisibility.shared);
      }

      // Build the share link and message
      final shareLink = conversationShareUrl(widget.conversation.id);
      final message = l10n.heresWhatWeDiscussed(shareLink);

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
        PlatformManager.instance.analytics.shareToContactsSmsOpened(widget.conversation.id, selected.length);
        HapticFeedback.mediumImpact();
        if (mounted) {
          Navigator.of(context).pop();
        }
        await launchUrl(smsUri);
      } else {
        setState(() {
          _isPreparingShare = false;
          _errorMessage = l10n.couldNotOpenSmsApp;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isPreparingShare = false;
        _errorMessage = '${context.l10n.error}: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final selectedCount = _selectedContacts.length;
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.75,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.sm),
            child: Text(
              context.l10n.selectContactsToShareSummary,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: OmiSearchField(
              placeholder: context.l10n.searchContactsHint,
              controller: _searchController,
              onChanged: _filterContacts,
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          if (selectedCount > 0)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xxs),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
                    decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
                    child: Text(
                      context.l10n.contactsSelectedCount(selectedCount),
                      style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),
                  const Spacer(),
                  OmiButton.tertiary(
                    label: context.l10n.clearAllSelection,
                    size: OmiButtonSize.compact,
                    onPressed: () => setState(() {
                      for (var contact in _contacts) {
                        contact.isSelected = false;
                      }
                    }),
                  ),
                ],
              ),
            ),
          if (_errorMessage != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
              child: Container(
                padding: const EdgeInsets.all(OmiSpacing.sm),
                decoration: const BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.smAll),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: OmiColors.danger, size: 20),
                    const SizedBox(width: OmiSpacing.xs),
                    Expanded(
                      child: Text(_errorMessage!, style: OmiType.footnote.copyWith(color: OmiColors.textPrimary)),
                    ),
                  ],
                ),
              ),
            ),
          Expanded(child: _buildContactsList(null)),
          if (!_permissionDenied)
            Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: OmiButton(
                expand: true,
                isLoading: _isPreparingShare,
                label: selectedCount == 0
                    ? context.l10n.selectContactsToShare
                    : selectedCount > 1
                        ? context.l10n.shareWithContactsCount(selectedCount)
                        : context.l10n.shareWithContactCount(selectedCount),
                onPressed: selectedCount == 0 ? null : _openNativeSms,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildContactsList(ScrollController? scrollController) {
    if (_isLoading) {
      return const OmiLoadingState();
    }

    if (_permissionDenied) {
      return OmiEmptyState(
        icon: Icons.contacts,
        title: context.l10n.contactsPermissionRequired,
        message: context.l10n.grantContactsPermissionForSms,
        action: OmiButton(
          label: context.l10n.openSettings,
          size: OmiButtonSize.compact,
          onPressed: () async {
            if (Platform.isIOS) {
              await launchUrl(Uri.parse('app-settings:'));
            } else {
              await launchUrl(Uri.parse('package:com.friend.ios'));
            }
          },
        ),
      );
    }

    if (_filteredContacts.isEmpty) {
      return OmiEmptyState(
        icon: Icons.search_off,
        title: _searchController.text.isEmpty
            ? context.l10n.noContactsWithPhoneNumbers
            : context.l10n.noContactsMatchSearch,
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
      selected: contact.isSelected,
      leading: CircleAvatar(
        backgroundColor: contact.isSelected ? OmiColors.accent : OmiColors.surface3,
        child: contact.isSelected
            ? const Icon(Icons.check, color: OmiColors.onAccent, size: 20)
            : Text(
                contact.displayName.isNotEmpty ? contact.displayName[0].toUpperCase() : '?',
                style: OmiType.headline,
              ),
      ),
      title: Text(
        contact.displayName,
        style: OmiType.subhead.copyWith(fontWeight: contact.isSelected ? FontWeight.w600 : FontWeight.normal),
      ),
      subtitle: Text(contact.phoneNumber, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
      trailing: contact.isSelected
          ? const Icon(Icons.check_circle, color: OmiColors.accent)
          : const Icon(Icons.circle_outlined, color: OmiColors.textTertiary),
    );
  }
}
