import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/device/page.dart';
import 'package:friend_private/pages/device/settings.dart';
import 'package:friend_private/pages/device/widgets/transcript.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/utils/notifications.dart';

class HomePageWrapper extends StatefulWidget {
  final dynamic btDevice;

  const HomePageWrapper({super.key, this.btDevice});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey = GlobalKey();
  int _selectedIndex = 1;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox()];
  List<MemoryRecord> memories = [];
  bool deepgramApiIsVisible = false;
  bool openaiApiIsVisible = false;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  final _gcpCredentialsController = TextEditingController();
  final _gcpBucketNameController = TextEditingController();
  final _customWebsocketUrlController = TextEditingController();
  bool _useFriendApiKeys = true;
  String _selectedLanguage = 'en';

  _initiateMemories() async {
    memories = await MemoryStorage.getAllMemories(filterOutUseless: true);
    setState(() {});
  }

  @override
  void initState() {
    // _refreshMemories();
    _initiateMemories();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      requestNotificationPermissions();
    });
    super.initState();
  }

  Future<void> _showSettingsBottomSheet() async {
    // Load API keys from shared preferences
    final prefs = SharedPreferencesUtil();
    _deepgramApiKeyController.text = prefs.deepgramApiKey;
    _openaiApiKeyController.text = prefs.openAIApiKey;
    _gcpCredentialsController.text = prefs.gcpCredentials;
    _gcpBucketNameController.text = prefs.gcpBucketName;
    _customWebsocketUrlController.text = SharedPreferencesUtil().customWebsocketUrl;
    _selectedLanguage = prefs.recordingsLanguage;
    _useFriendApiKeys = prefs.useFriendApiKeys;

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20.0),
          topRight: Radius.circular(20.0),
        ),
      ),
      builder: (BuildContext context) {
        return PopScope(
            canPop: true,
            child: StatefulBuilder(
              builder: (context, StateSetter setModalState) {
                return SettingsBottomSheet(
                  deepgramApiKeyController: _deepgramApiKeyController,
                  openaiApiKeyController: _openaiApiKeyController,
                  deepgramApiIsVisible: deepgramApiIsVisible,
                  openaiApiIsVisible: openaiApiIsVisible,
                  gcpCredentialsController: _gcpCredentialsController,
                  gcpBucketNameController: _gcpBucketNameController,
                  customWebsocketUrlController: _customWebsocketUrlController,
                  selectedLanguage: _selectedLanguage,
                  onLanguageSelected: (String value) {
                    setModalState(() {
                      _selectedLanguage = value;
                    });
                  },
                  useFriendAPIKeys: _useFriendApiKeys,
                  onUseFriendAPIKeysChanged: (bool? value) {
                    setModalState(() {
                      _useFriendApiKeys = value ?? true;
                    });
                  },
                  deepgramApiVisibilityCallback: () {
                    setModalState(() {
                      deepgramApiIsVisible = !deepgramApiIsVisible;
                    });
                  },
                  openaiApiVisibilityCallback: () {
                    setModalState(() {
                      openaiApiIsVisible = !openaiApiIsVisible;
                    });
                  },
                  saveSettings: _saveSettings,
                );
              },
            ));
      },
    );
  }

  void _saveSettings() async {
    final prefs = SharedPreferencesUtil();
    prefs.openAIApiKey = _openaiApiKeyController.text.trim();
    prefs.gcpCredentials = _gcpCredentialsController.text.trim();
    prefs.gcpBucketName = _gcpBucketNameController.text.trim();

    bool requiresReset = false;
    if (_selectedLanguage != prefs.recordingsLanguage) {
      prefs.recordingsLanguage = _selectedLanguage;
      requiresReset = true;
    }
    if (_deepgramApiKeyController.text != prefs.deepgramApiKey) {
      prefs.deepgramApiKey = _deepgramApiKeyController.text.trim();
      requiresReset = true;
    }
    if (_customWebsocketUrlController.text != prefs.customWebsocketUrl) {
      prefs.customWebsocketUrl = _customWebsocketUrlController.text.trim();
      requiresReset = true;
    }
    if (_useFriendApiKeys != prefs.useFriendApiKeys) {
      requiresReset = true;
      prefs.useFriendApiKeys = _useFriendApiKeys;
    }
    if (requiresReset) transcriptChildWidgetKey.currentState?.resetState();

    if (_gcpCredentialsController.text.isNotEmpty && _gcpBucketNameController.text.isNotEmpty) {
      authenticateGCP();
    }
  }

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: IndexedStack(
          index: _selectedIndex,
          children: [
            MemoriesPage(
              memories: memories,
              refreshMemories: _initiateMemories,
            ),
            HomePage(
                btDevice: widget.btDevice,
                refreshMemories: _initiateMemories,
                transcriptChildWidgetKey: transcriptChildWidgetKey),
            const ChatPage(),
          ],
        ),
      ),
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        title: Text(['Memories', 'Device', 'Chat'][_selectedIndex]),
        elevation: 2.0,
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(
              Icons.settings,
              color: Colors.white,
              size: 30,
            ),
            onPressed: _showSettingsBottomSheet,
          )
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        elevation: 0,
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: Icon(Icons.history),
            label: 'Memories',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.bluetooth_connected),
            label: 'Device',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.chat),
            label: 'Chat',
          ),
        ],
        currentIndex: _selectedIndex,
        selectedItemColor: Colors.white,
        unselectedItemColor: Colors.grey.shade700,
        onTap: _onItemTapped,
      ),
    );
  }

  @override
  void dispose() {
    _deepgramApiKeyController.dispose();
    _openaiApiKeyController.dispose();
    _gcpCredentialsController.dispose();
    _gcpBucketNameController.dispose();
    _customWebsocketUrlController.dispose();
    super.dispose();
  }
}
