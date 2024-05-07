import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../backend/api_requests/api_calls.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import '/pages/ble/device_data/widget.dart';
import 'model.dart';

export 'model.dart';

class ConnectDeviceWidget extends StatefulWidget {
  const ConnectDeviceWidget({
    super.key,
    required this.btDevice,
  });

  final dynamic btDevice;

  @override
  State<ConnectDeviceWidget> createState() => _ConnectDeviceWidgetState();
}

class _ConnectDeviceWidgetState extends State<ConnectDeviceWidget> {
  GlobalKey<DeviceDataWidgetState> childWidgetKey = GlobalKey();
  late ConnectDeviceModel _model;
  bool deepgramApiIsVisible = false;
  bool openaiApiIsVisible = false;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  bool _areApiKeysSet = false;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ConnectDeviceModel());
    authenticateGCP();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Check if the API keys are set
      final prefs = await SharedPreferences.getInstance();
      final deepgramApiKey = prefs.getString('deepgramApiKey');
      final openaiApiKey = prefs.getString('openaiApiKey');

      if (deepgramApiKey != null && deepgramApiKey.isNotEmpty && openaiApiKey != null && openaiApiKey.isNotEmpty) {
        // If both API keys are set, initialize the page and enable the DeviceDataWidget
        _initializePage();
        setState(() {
          _areApiKeysSet = true;
        });
      } else {
        // If any of the API keys are not set, show the settings bottom sheet
        _showSettingsBottomSheet();
      }
    });
  }

  void _initializePage() {
    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      setState(() {
        _model.currentRssi = BTDeviceStruct.maybeFromMap(widget.btDevice)?.rssi;
      });
      _model.rssiUpdateTimer = InstantTimer.periodic(
        duration: const Duration(milliseconds: 2000),
        callback: (timer) async {
          _model.updatedRssi = await actions.ble0getRssi(
            BTDeviceStruct.maybeFromMap(widget.btDevice!)!,
          );
          setState(() {
            _model.currentRssi = _model.updatedRssi;
          });
        },
        startImmediately: true,
      );
    });
  }

  @override
  void dispose() {
    _model.dispose();
    _deepgramApiKeyController.dispose();
    _openaiApiKeyController.dispose();
    super.dispose();
  }

  String _selectedLanguage = 'en';

  Future<void> _showSettingsBottomSheet() async {
    // Load API keys from shared preferences
    final prefs = await SharedPreferences.getInstance();
    final deepgramApiKey = prefs.getString('deepgramApiKey') ?? '';
    final openaiApiKey = prefs.getString('openaiApiKey') ?? '';
    final recordingsLanguage = prefs.getString('recordingsLanguage') ?? 'en';

    _deepgramApiKeyController.text = deepgramApiKey;
    _openaiApiKeyController.text = openaiApiKey;
    _selectedLanguage = recordingsLanguage;

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
          canPop: false,
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setModalState) {
              return Padding(
                padding: EdgeInsets.only(
                  bottom: MediaQuery.of(context).viewInsets.bottom,
                ),
                child: Container(
                  height: MediaQuery.of(context).size.height * 0.7,
                  padding: const EdgeInsets.all(16.0),
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'Settings',
                          style: TextStyle(
                            fontSize: 20.0,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 16.0),
                        const Text(
                          'Deepgram API Key is used for converting speech to text.',
                          style: TextStyle(
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 8.0),
                        TextField(
                          controller: _deepgramApiKeyController,
                          obscureText: deepgramApiIsVisible ? false : true,
                          decoration: InputDecoration(
                            labelText: 'Deepgram API Key',
                            labelStyle: const TextStyle(color: Colors.white),
                            border: const OutlineInputBorder(),
                            enabledBorder: const OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                              borderRadius: BorderRadius.all(Radius.circular(20.0)),
                            ),
                            focusedBorder: const OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                            ),
                            suffixIcon: IconButton(
                              icon: Icon(
                                deepgramApiIsVisible ? Icons.visibility : Icons.visibility_off,
                                color: Theme.of(context).primaryColor,
                              ),
                              onPressed: () {
                                setModalState(() {
                                  deepgramApiIsVisible = !deepgramApiIsVisible;
                                });
                              },
                            ),
                          ),
                          style: const TextStyle(color: Colors.white),
                        ),
                        const SizedBox(height: 8.0),
                        TextButton(
                          onPressed: () {
                            launch('https://developers.deepgram.com/docs/create-additional-api-keys');
                          },
                          child: const Text(
                            'How to generate a Deepgram API key?',
                            style: TextStyle(
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        const SizedBox(height: 16.0),
                        const Text(
                          'OpenAI API Key is used for chat.',
                          style: TextStyle(
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 8.0),
                        TextField(
                          controller: _openaiApiKeyController,
                          obscureText: openaiApiIsVisible ? false : true,
                          autocorrect: false,
                          enableSuggestions: false,
                          decoration: InputDecoration(
                              labelText: 'OpenAI API Key',
                              labelStyle: const TextStyle(color: Colors.white),
                              border: const OutlineInputBorder(),
                              enabledBorder: const OutlineInputBorder(
                                borderSide: BorderSide(color: Colors.white),
                                borderRadius: BorderRadius.all(Radius.circular(20.0)),
                              ),
                              focusedBorder: const OutlineInputBorder(
                                borderSide: BorderSide(color: Colors.white),
                              ),
                              suffixIcon: IconButton(
                                icon: Icon(
                                  openaiApiIsVisible ? Icons.visibility : Icons.visibility_off,
                                  color: Theme.of(context).primaryColor,
                                ),
                                onPressed: () {
                                  setModalState(() {
                                    openaiApiIsVisible = !openaiApiIsVisible;
                                  });
                                },
                              )),
                          style: const TextStyle(color: Colors.white),
                        ),
                        const SizedBox(height: 8.0),
                        TextButton(
                          onPressed: () {
                            launch('https://platform.openai.com/api-keys');
                          },
                          child: const Text(
                            'How to generate an OpenAI API key?',
                            style: TextStyle(
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        const SizedBox(height: 16.0),
                        const Center(child: Text('Recordings Language:', style: TextStyle(color: Colors.white))),
                        const SizedBox(height: 12),
                        Container(
                          height: 50,
                          decoration: BoxDecoration(
                            border: Border.all(color: Colors.white),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
                          child: DropdownButton<String>(
                            menuMaxHeight: 350,
                            value: _selectedLanguage,
                            onChanged: (String? newValue) {
                              setModalState(() {
                                _selectedLanguage = newValue!;
                                debugPrint('Selecting: $newValue');
                              });
                            },
                            dropdownColor: Colors.black,
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                            underline: Container(
                              height: 0,
                              color: Colors.white,
                            ),
                            isExpanded: false,
                            itemHeight: 48,
                            items: availableLanguages.keys.map<DropdownMenuItem<String>>((String key) {
                              return DropdownMenuItem<String>(
                                value: availableLanguages[key],
                                child: Text(
                                  '$key (${availableLanguages[key]})',
                                  style: TextStyle(
                                      color: _selectedLanguage == availableLanguages[key]
                                          ? Colors.blue[400]
                                          : Colors.white,
                                      fontSize: 16),
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                        const SizedBox(height: 20),
                        ElevatedButton(
                          onPressed: () {
                            String deepgramApiKey = _deepgramApiKeyController.text;
                            String openaiApiKey = _openaiApiKeyController.text;

                            if (deepgramApiKey.isNotEmpty && openaiApiKey.isNotEmpty) {
                              _saveApiKeys(deepgramApiKey, openaiApiKey);
                              Navigator.pop(context);
                            } else {
                              // Show a popup dialog if either of the API keys is empty
                              showDialog(
                                context: context,
                                builder: (BuildContext context) {
                                  return AlertDialog(
                                    title: const Text('Error'),
                                    content: const Text('Please provide both API keys'),
                                    actions: [
                                      TextButton(
                                        onPressed: () {
                                          Navigator.pop(context);
                                        },
                                        child: const Text('OK'),
                                      ),
                                    ],
                                  );
                                },
                              );
                            }
                          },
                          style: ButtonStyle(
                            backgroundColor: MaterialStateProperty.all<Color>(Colors.white),
                            shape: MaterialStateProperty.all<RoundedRectangleBorder>(
                              RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(20.0),
                              ),
                            ),
                            overlayColor: MaterialStateProperty.resolveWith<Color>(
                              (Set<MaterialState> states) {
                                if (states.contains(MaterialState.pressed)) {
                                  return Colors.grey[200]!;
                                }
                                return Colors.transparent;
                              },
                            ),
                          ),
                          child: const Text(
                            'Save',
                            style: TextStyle(color: Colors.black),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        );
      },
    );
// Set the obscured API keys in the text fields
    setState(() {
      _deepgramApiKeyController.text = deepgramApiKey;
      _openaiApiKeyController.text = openaiApiKey;
    });
  }

  void _saveApiKeys(String deepgramApiKey, String openaiApiKey) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('deepgramApiKey', deepgramApiKey);
    await prefs.setString('openaiApiKey', openaiApiKey);
    if (_selectedLanguage != prefs.getString('recordingsLanguage')) {
      // If the language has changed, restart the deepgram websocket
      childWidgetKey.currentState?.resetState();
      await prefs.setString('recordingsLanguage', _selectedLanguage);
    }
    // Initialize the page and enable the DeviceDataWidget after saving the API keys
    _initializePage();
    setState(() {
      _areApiKeysSet = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _model.unfocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(_model.unfocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        appBar: AppBar(
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
        ),
        body: Stack(
          children: [
            wrapWithModel(
              model: _model.blurModel,
              updateCallback: () => setState(() {}),
              child: const BlurBotWidget(),
            ),
            ListView(children: [
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
                        useGoogleFonts:
                            GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).headlineLargeFamily),
                      ),
                ),
              ),
              const SizedBox(height: 8),
              Center(
                  child: Text(
                BTDeviceStruct.maybeFromMap(widget.btDevice)?.name ?? '-',
                style: _getTextStyle(),
              )),
              const SizedBox(height: 8),
              Center(
                  child: Text(
                BTDeviceStruct.maybeFromMap(widget.btDevice)?.id ?? '-',
                style: _getTextStyle(),
              )),
              const SizedBox(height: 32),
              _areApiKeysSet
                  ? DeviceDataWidget(
                      btDevice: BTDeviceStruct.maybeFromMap(widget.btDevice!)!,
                      key: childWidgetKey,
                    )
                  : const SizedBox.shrink(),
            ]),
          ],
        ),
      ),
    );
  }

  _getTextStyle() {
    return FlutterFlowTheme.of(context).titleSmall.override(
          fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
          letterSpacing: 0.0,
          useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
        );
  }
}
