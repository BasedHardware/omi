import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:friend_private/pages/home/settings.dart';
import 'package:friend_private/utils/scan.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:friend_private/widgets/scanning_animation.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'widget.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.btDevice,
  });

  final dynamic btDevice;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  GlobalKey<DeviceDataWidgetState> childWidgetKey = GlobalKey();
  BTDeviceStruct? _device;
  bool deepgramApiIsVisible = false;
  bool openaiApiIsVisible = false;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  final _gcpCredentialsController = TextEditingController();
  final _gcpBucketNameController = TextEditingController();
  bool _areApiKeysSet = false;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  String _selectedLanguage = 'en';
  final unFocusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    if (widget.btDevice != null) {
      _device = BTDeviceStruct.maybeFromMap(widget.btDevice);
    } else {
      scanAndConnectDevice().then((friendDevice) {
        if (friendDevice != null) {
          setState(() {
            _device = friendDevice;
          });
        }
      });
    }
    authenticateGCP();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Check if the API keys are set
      final prefs = await SharedPreferences.getInstance();
      final deepgramApiKey = prefs.getString('deepgramApiKey');
      final openaiApiKey = prefs.getString('openaiApiKey');

      if ((deepgramApiKey?.isNotEmpty ?? false) && (openaiApiKey?.isNotEmpty ?? false)) {
        // If both API keys are set, initialize the page and enable the DeviceDataWidget
        setState(() {
          _areApiKeysSet = true;
        });
      } else {
        // If any of the API keys are not set, show the settings bottom sheet
        _showSettingsBottomSheet();
      }
    });
  }

  @override
  void dispose() {
    _deepgramApiKeyController.dispose();
    _openaiApiKeyController.dispose();
    _gcpCredentialsController.dispose();
    _gcpBucketNameController.dispose();
    unFocusNode.dispose();
    super.dispose();
  }

  Future<void> _showSettingsBottomSheet() async {
    // Load API keys from shared preferences
    final prefs = await SharedPreferences.getInstance();
    _deepgramApiKeyController.text = prefs.getString('deepgramApiKey') ?? '';
    _openaiApiKeyController.text = prefs.getString('openaiApiKey') ?? '';
    _gcpCredentialsController.text = prefs.getString('gcpCredentials') ?? '';
    _gcpBucketNameController.text = prefs.getString('gcpBucketName') ?? '';
    _selectedLanguage = prefs.getString('recordingsLanguage') ?? 'en';

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
            canPop: _areApiKeysSet,
            child: StatefulBuilder(
              builder: (context, StateSetter setModalState) {
                return SettingsBottomSheet(
                  areApiKeysSet: _areApiKeysSet,
                  deepgramApiKeyController: _deepgramApiKeyController,
                  openaiApiKeyController: _openaiApiKeyController,
                  deepgramApiIsVisible: deepgramApiIsVisible,
                  openaiApiIsVisible: openaiApiIsVisible,
                  gcpCredentialsController: _gcpCredentialsController,
                  gcpBucketNameController: _gcpBucketNameController,
                  selectedLanguage: _selectedLanguage,
                  onLanguageSelected: (String value) {
                    setModalState(() {
                      _selectedLanguage = value;
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
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('openaiApiKey', _openaiApiKeyController.text.trim());
    await prefs.setString('gcpCredentials', _gcpCredentialsController.text.trim());
    await prefs.setString('gcpBucketName', _gcpBucketNameController.text.trim());

    if (_selectedLanguage != prefs.getString('recordingsLanguage')) {
      await prefs.setString('recordingsLanguage', _selectedLanguage);
      // If the language has changed, restart the deepgram websocket
      childWidgetKey.currentState?.resetState();
    } else if (_deepgramApiKeyController.text != prefs.getString('deepgramApiKey')) {
      await prefs.setString('deepgramApiKey', _deepgramApiKeyController.text.trim());
      childWidgetKey.currentState?.resetState();
    }

    if (_gcpCredentialsController.text.isNotEmpty && _gcpBucketNameController.text.isNotEmpty) {
      authenticateGCP();
    }
    setState(() {
      _areApiKeysSet = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => unFocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(unFocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        appBar: _getAppBar(),
        body: Stack(
          children: [
            const BlurBotWidget(),
            ListView(children: [
              ..._getConnectedDeviceWidgets(),
              _areApiKeysSet && _device != null
                  ? DeviceDataWidget(
                      btDevice: _device!,
                      key: childWidgetKey,
                    )
                  : const SizedBox.shrink(),
            ]),
          ],
        ),
      ),
    );
  }

  _getAppBar() {
    return AppBar(
      backgroundColor: FlutterFlowTheme.of(context).primary,
      automaticallyImplyLeading: false,
      title: FFButtonWidget(
        onPressed: () async {
          context.pushNamed('memoriesPage');
        },
        text: 'Memories ↗',
        options: FFButtonOptions(
          padding: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 0.0),
          iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
          color: FlutterFlowTheme.of(context).primary,
          textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                color: const Color(0xFFF7F4F4),
                fontSize: 18.0,
                fontWeight: FontWeight.bold,
                useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
              ),
          elevation: 0.0,
          borderSide: const BorderSide(
            color: Colors.transparent,
            width: 0.0,
          ),
          borderRadius: BorderRadius.circular(24.0),
        ),
      ),
      actions: [
        IconButton(
          icon: const Icon(
            Icons.settings,
            color: Colors.white,
            size: 30,
          ),
          onPressed: _showSettingsBottomSheet,
        ),
      ],
      centerTitle: false,
      elevation: 2.0,
    );
  }

  _getTextStyle() {
    return FlutterFlowTheme.of(context).titleSmall.override(
          fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
          letterSpacing: 0.0,
          useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
        );
  }

  _getConnectedDeviceWidgets() {
    if (_device == null) {
      return [
        const SizedBox(height: 64),
        const ScanningAnimation(),
        const ScanningUI(
          string1: 'Looking for Friend wearable',
          string2: 'Locating your Friend device. Keep it near your phone for pairing',
        ),
      ];
    }
    return [
      const SizedBox(height: 64),
      Center(
          child: ClipRRect(
        borderRadius: BorderRadius.circular(24.0),
        child: Image.network(
          'https://images.unsplash.com/photo-1589128777073-263566ae5e4d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w0NTYyMDF8MHwxfHNlYXJjaHwyfHxuZWNrbGFjZXxlbnwwfHx8fDE3MTEyMDQxNTF8MA&ixlib=rb-4.0.3&q=80&w=1080',
          width: 120.0,
          height: 120.0,
          fit: BoxFit.cover,
          alignment: const Alignment(0.0, 1.0),
        ),
      )),
      const SizedBox(height: 16),
      Center(
        child: Text(
          'Connected Device',
          style: FlutterFlowTheme.of(context).headlineLarge.override(
                fontFamily: FlutterFlowTheme.of(context).headlineLargeFamily,
                fontSize: 24.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.bold,
                useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).headlineLargeFamily),
              ),
        ),
      ),
      const SizedBox(height: 8),
      Center(child: Text(_device?.name ?? '-', style: _getTextStyle())),
      const SizedBox(height: 8),
      Center(child: Text(_device?.id ?? '-', style: _getTextStyle())),
      const SizedBox(height: 32),
    ];
  }
}
