import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import '/pages/ble/device_data/device_data_widget.dart';
import 'connect_device_model.dart';

export 'connect_device_model.dart';

class ConnectDeviceWidget extends StatefulWidget {
  const ConnectDeviceWidget({
    super.key,
    required this.btdevice,
  });

  final dynamic btdevice;

  @override
  State<ConnectDeviceWidget> createState() => _ConnectDeviceWidgetState();
}

class _ConnectDeviceWidgetState extends State<ConnectDeviceWidget> {
  late ConnectDeviceModel _model;
  final _deepgramApiKeyController = TextEditingController();
  final _openaiApiKeyController = TextEditingController();
  bool _areApiKeysSet = false;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ConnectDeviceModel());

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Check if the API keys are set
      final prefs = await SharedPreferences.getInstance();
      final deepgramApiKey = prefs.getString('deepgramApiKey');
      final openaiApiKey = prefs.getString('openaiApiKey');

      if (deepgramApiKey != null &&
          deepgramApiKey.isNotEmpty &&
          openaiApiKey != null &&
          openaiApiKey.isNotEmpty) {
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
        _model.currentRssi = BTDeviceStruct.maybeFromMap(widget.btdevice)?.rssi;
      });
      _model.rssiUpdateTimer = InstantTimer.periodic(
        duration: Duration(milliseconds: 2000),
        callback: (timer) async {
          _model.updatedRssi = await actions.ble0getRssi(
            BTDeviceStruct.maybeFromMap(widget.btdevice!)!,
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

  String _obscureApiKey(String apiKey) {
    if (apiKey.length <= 3) {
      return apiKey;
    } else {
      final obscuredKey = '*' * (apiKey.length - 3);
      return apiKey.substring(0, 3) + obscuredKey;
    }
  }

  Future<void> _showSettingsBottomSheet() async {
    // Load API keys from shared preferences
    final prefs = await SharedPreferences.getInstance();
    final deepgramApiKey = prefs.getString('deepgramApiKey') ?? '';
    final openaiApiKey = prefs.getString('openaiApiKey') ?? '';

    _deepgramApiKeyController.text = _obscureApiKey(deepgramApiKey);
    _openaiApiKeyController.text = _obscureApiKey(openaiApiKey);

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20.0),
          topRight: Radius.circular(20.0),
        ),
      ),
      builder: (BuildContext context) {
        return WillPopScope(
          onWillPop: () async => false,
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setModalState) {
              return Padding(
                padding: EdgeInsets.only(
                  bottom: MediaQuery.of(context).viewInsets.bottom,
                ),
                child: Container(
                  height: MediaQuery.of(context).size.height * 0.6,
                  padding: EdgeInsets.all(16.0),
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'Settings',
                          style: TextStyle(
                            fontSize: 20.0,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        SizedBox(height: 16.0),
                        Text(
                          'Deepgram API Key is used for converting speech to text.',
                          style: TextStyle(
                            color: Colors.white,
                          ),
                        ),
                        SizedBox(height: 8.0),
                        TextField(
                          controller: _deepgramApiKeyController,
                          decoration: InputDecoration(
                            labelText: 'Deepgram API Key',
                            labelStyle: TextStyle(color: Colors.white),
                            border: OutlineInputBorder(),
                            enabledBorder: OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                              borderRadius:
                                  const BorderRadius.all(Radius.circular(20.0)),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                            ),
                          ),
                          style: TextStyle(color: Colors.white),
                        ),
                        SizedBox(height: 8.0),
                        TextButton(
                          onPressed: () {
                            launch(
                                'https://developers.deepgram.com/docs/create-additional-api-keys');
                          },
                          child: Text(
                            'How to generate a Deepgram API key?',
                            style: TextStyle(
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        SizedBox(height: 16.0),
                        Text(
                          'OpenAI API Key is used for chat.',
                          style: TextStyle(
                            color: Colors.white,
                          ),
                        ),
                        SizedBox(height: 8.0),
                        TextField(
                          controller: _openaiApiKeyController,
                          decoration: InputDecoration(
                            labelText: 'OpenAI API Key',
                            labelStyle: TextStyle(color: Colors.white),
                            border: OutlineInputBorder(),
                            enabledBorder: OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                              borderRadius:
                                  const BorderRadius.all(Radius.circular(20.0)),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderSide: BorderSide(color: Colors.white),
                            ),
                          ),
                          style: TextStyle(color: Colors.white),
                        ),
                        SizedBox(height: 8.0),
                        TextButton(
                          onPressed: () {
                            launch('https://platform.openai.com/api-keys');
                          },
                          child: Text(
                            'How to generate an OpenAI API key?',
                            style: TextStyle(
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        SizedBox(height: 16.0),
                        ElevatedButton(
                          onPressed: () {
                            String deepgramApiKey =
                                _deepgramApiKeyController.text;
                            String openaiApiKey = _openaiApiKeyController.text;

                            if (deepgramApiKey.isNotEmpty &&
                                 openaiApiKey.isNotEmpty) {
                              _saveApiKeys(deepgramApiKey, openaiApiKey);
                              Navigator.pop(context);
                            } else {
                              // Show a popup dialog if either of the API keys is empty
                              showDialog(
                                context: context,
                                builder: (BuildContext context) {
                                  return AlertDialog(
                                    title: Text('Error'),
                                    content:
                                        Text('Please provide both API keys'),
                                    actions: [
                                      TextButton(
                                        onPressed: () {
                                          Navigator.pop(context);
                                        },
                                        child: Text('OK'),
                                      ),
                                    ],
                                  );
                                },
                              );
                            }
                          },
                          style: ButtonStyle(
                            backgroundColor:
                                MaterialStateProperty.all<Color>(Colors.white),
                            shape: MaterialStateProperty.all<
                                RoundedRectangleBorder>(
                              RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(20.0),
                              ),
                            ),
                            overlayColor:
                                MaterialStateProperty.resolveWith<Color>(
                              (Set<MaterialState> states) {
                                if (states.contains(MaterialState.pressed)) {
                                  return Colors.grey[200]!;
                                }
                                return Colors.transparent;
                              },
                            ),
                          ),
                          child: Text(
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
      _deepgramApiKeyController.text = _obscureApiKey(deepgramApiKey);
      _openaiApiKeyController.text = _obscureApiKey(openaiApiKey);
    });
  }

  void _saveApiKeys(String deepgramApiKey, String openaiApiKey) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('deepgramApiKey', deepgramApiKey);
    await prefs.setString('openaiApiKey', openaiApiKey);

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
          title: InkWell(
            splashColor: Colors.transparent,
            focusColor: Colors.transparent,
            hoverColor: Colors.transparent,
            highlightColor: Colors.transparent,
            onTap: () async {
              context.pushNamed('chatPage');
            },
            child: Text(
              'Chat',
              style: FlutterFlowTheme.of(context).headlineMedium.override(
                    fontFamily:
                        FlutterFlowTheme.of(context).headlineMediumFamily,
                    color: Colors.white,
                    fontSize: 22.0,
                    letterSpacing: 0.0,
                    useGoogleFonts: GoogleFonts.asMap().containsKey(
                        FlutterFlowTheme.of(context).headlineMediumFamily),
                  ),
            ),
          ),
          actions: [
            IconButton(
              icon: Icon(
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
              child: BlurBotWidget(),
            ),
            Align(
              alignment: AlignmentDirectional(0.0, 0.0),
              child: Column(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.max,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(24.0),
                        child: Image.network(
                          'https://images.unsplash.com/photo-1589128777073-263566ae5e4d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w0NTYyMDF8MHwxfHNlYXJjaHwyfHxuZWNrbGFjZXxlbnwwfHx8fDE3MTEyMDQxNTF8MA&ixlib=rb-4.0.3&q=80&w=1080',
                          width: 120.0,
                          height: 120.0,
                          fit: BoxFit.cover,
                          alignment: Alignment(0.0, 1.0),
                        ),
                      ),
                      Align(
                        alignment: AlignmentDirectional(0.0, 0.0),
                        child: Text(
                          'Connected Device',
                          style: FlutterFlowTheme.of(context)
                              .headlineLarge
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .headlineLargeFamily,
                                fontSize: 24.0,
                                letterSpacing: 0.0,
                                fontWeight: FontWeight.bold,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .headlineLargeFamily),
                              ),
                        ),
                      ),
                      Column(
                        mainAxisSize: MainAxisSize.max,
                        children: [
                          Align(
                            alignment: AlignmentDirectional(0.0, 0.0),
                            child: Text(
                              valueOrDefault<String>(
                                BTDeviceStruct.maybeFromMap(widget.btdevice)
                                    ?.name,
                                '-',
                              ),
                              style: FlutterFlowTheme.of(context)
                                  .titleSmall
                                  .override(
                                    fontFamily: FlutterFlowTheme.of(context)
                                        .titleSmallFamily,
                                    letterSpacing: 0.0,
                                    useGoogleFonts: GoogleFonts.asMap()
                                        .containsKey(
                                            FlutterFlowTheme.of(context)
                                                .titleSmallFamily),
                                  ),
                            ),
                          ),
                          Align(
                            alignment: AlignmentDirectional(0.0, 0.0),
                            child: Text(
                              valueOrDefault<String>(
                                BTDeviceStruct.maybeFromMap(widget.btdevice)
                                    ?.id,
                                '-',
                              ),
                              style: FlutterFlowTheme.of(context)
                                  .titleSmall
                                  .override(
                                    fontFamily: FlutterFlowTheme.of(context)
                                        .titleSmallFamily,
                                    letterSpacing: 0.0,
                                    useGoogleFonts: GoogleFonts.asMap()
                                        .containsKey(
                                            FlutterFlowTheme.of(context)
                                                .titleSmallFamily),
                                  ),
                            ),
                          ),
                        ].divide(SizedBox(height: 8.0)),
                      ),
                    ].divide(SizedBox(height: 16.0)),
                  ),
                  Expanded(
                    child: Align(
                      alignment: AlignmentDirectional(0.0, 0.0),
                      child: _areApiKeysSet
                          ? wrapWithModel(
                              model: _model.deviceDataModel,
                              updateCallback: () => setState(() {}),
                              updateOnChange: true,
                              child: DeviceDataWidget(
                                btdevice: BTDeviceStruct.maybeFromMap(
                                    widget.btdevice!)!,
                              ),
                            )
                          : SizedBox.shrink(),
                    ),
                  ),
                ]
                    .divide(SizedBox(height: 32.0))
                    .addToStart(SizedBox(height: 48.0))
                    .addToEnd(SizedBox(height: 48.0)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
