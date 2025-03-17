import 'dart:io';
import 'dart:async';
import 'dart:math' show sin, Random;
import 'dart:collection' show Queue;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/chat/select_text_screen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/animated_mini_banner.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'widgets/message_action_menu.dart';

class ChatPage extends StatefulWidget {
  final bool isPivotBottom;

  const ChatPage({
    super.key,
    this.isPivotBottom = false,
  });

  @override
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _isListening = false;
  String _recognizedText = '';

  bool isScrollingDown = false;

  bool _showSendButton = false;
  bool _isRecording = false;

  var prefs = SharedPreferencesUtil();
  late List<App> apps;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  // Keep track of the most recent transcription
  List<TranscriptSegment> _lastTranscriptSegments = [];

  Timer? _recordingTimer;
  int _recordingDuration = 0;

  double _currentSoundLevel = 0;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    apps = prefs.appsList;
    scrollController = ScrollController();
    scrollController.addListener(() {
      if (scrollController.position.userScrollDirection == ScrollDirection.reverse) {
        if (!isScrollingDown) {
          isScrollingDown = true;
          setState(() {});
          Future.delayed(const Duration(seconds: 5), () {
            if (isScrollingDown) {
              isScrollingDown = false;
              if (mounted) {
                setState(() {});
              }
            }
          });
        }
      }

      if (scrollController.position.userScrollDirection == ScrollDirection.forward) {
        if (isScrollingDown) {
          isScrollingDown = false;
          setState(() {});
        }
      }
    });
    
    // Initialize speech recognition
    _initializeSpeech();
    
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      scrollToBottom();
    });
    super.initState();
  }

  void _initializeSpeech() async {
    bool available = await _speech.initialize(
      onError: (error) => debugPrint('Speech recognition error: $error'),
      onStatus: (status) {
        if (status == 'done') {
          setState(() {
            _isListening = false;
            _isRecording = false;
            if (_recognizedText.isNotEmpty) {
              textController.text = _recognizedText;
              setShowSendButton();
            }
          });
        } else if (status == 'notListening') {
          setState(() {
            _isListening = false;
            _isRecording = false;
          });
        }
      },
    );
    if (!available) {
      debugPrint('Speech recognition not available');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Speech recognition is not available on this device.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _speech.cancel();
    textController.dispose();
    scrollController.dispose();
    super.dispose();
  }

  void setShowSendButton() {
    if (_showSendButton != textController.text.isNotEmpty) {
      setState(() {
        _showSendButton = textController.text.isNotEmpty;
      });
    }
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  Widget _buildRecordingOverlay() {
    if (!_isRecording) return const SizedBox.shrink();
    
    return Container(
      width: double.infinity,
      height: 120,
      margin: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom),
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.withOpacity(0.3)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () {
                  _toggleVoiceRecording();
                },
              ),
              Text(
                _formatDuration(_recordingDuration),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.check, color: Colors.white),
                onPressed: () {
                  _toggleVoiceRecording();
                },
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            height: 40,
            margin: const EdgeInsets.symmetric(horizontal: 20),
            child: CustomPaint(
              painter: WaveformPainter(soundLevel: _currentSoundLevel),
              size: Size.infinite,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer2<MessageProvider, ConnectivityProvider>(
      builder: (context, provider, connectivityProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: provider.isLoadingMessages
              ? AnimatedMiniBanner(
                  showAppBar: provider.isLoadingMessages,
                  child: Container(
                    width: double.infinity,
                    height: 10,
                    color: Colors.green,
                    child: const Center(
                      child: Text(
                        'Syncing messages with server...',
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
                    ),
                  ),
                )
              : null,
          body: Stack(
            children: [
              Align(
                alignment: Alignment.topCenter,
                child: provider.isLoadingMessages && !provider.hasCachedMessages
                    ? Column(
                        children: [
                          const SizedBox(height: 100),
                          const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            provider.firstTimeLoadingText,
                            style: const TextStyle(color: Colors.white),
                          ),
                        ],
                      )
                    : provider.isClearingChat
                        ? const Column(
                            children: [
                              SizedBox(height: 100),
                              CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                              SizedBox(height: 16),
                              Text(
                                "Deleting your messages from Omi's memory...",
                                style: TextStyle(color: Colors.white),
                              ),
                            ],
                          )
                        : (provider.messages.isEmpty)
                            ? Center(
                                child: Padding(
                                  padding: const EdgeInsets.only(bottom: 32.0),
                                  child: Text(
                                      connectivityProvider.isConnected
                                          ? 'No messages yet!\nWhy don\'t you start a conversation?'
                                          : 'Please check your internet connection and try again',
                                      textAlign: TextAlign.center,
                                      style: const TextStyle(color: Colors.white)),
                                ),
                              )
                            : ListView.builder(
                                shrinkWrap: true,
                                reverse: true,
                                controller: scrollController,
                                //  physics: const NeverScrollableScrollPhysics(),
                                itemCount: provider.messages.length,
                                itemBuilder: (context, chatIndex) {
                                  final message = provider.messages[chatIndex];
                                  double topPadding = chatIndex == provider.messages.length - 1 ? 24 : 16;
                                  if (chatIndex != 0) message.askForNps = false;

                                  double bottomPadding = chatIndex == 0
                                      ? provider.selectedFiles.isNotEmpty
                                          ? (Platform.isAndroid
                                              ? MediaQuery.sizeOf(context).height * 0.32
                                              : MediaQuery.sizeOf(context).height * 0.3)
                                          : (Platform.isAndroid
                                              ? MediaQuery.sizeOf(context).height * 0.21
                                              : MediaQuery.sizeOf(context).height * 0.19)
                                      : 0;
                                  return GestureDetector(
                                    onLongPress: () {
                                      showModalBottomSheet(
                                        context: context,
                                        shape: const RoundedRectangleBorder(
                                          borderRadius: BorderRadius.vertical(
                                            top: Radius.circular(20),
                                          ),
                                        ),
                                        builder: (context) => MessageActionMenu(
                                          message: message.text.decodeString,
                                          onCopy: () async {
                                            MixpanelManager()
                                                .track('Chat Message Copied', properties: {'message': message.text});
                                            await Clipboard.setData(ClipboardData(text: message.text.decodeString));
                                            if (context.mounted) {
                                              ScaffoldMessenger.of(context).showSnackBar(
                                                const SnackBar(
                                                  content: Text(
                                                    'Message copied to clipboard.',
                                                    style: TextStyle(
                                                      color: Color.fromARGB(255, 255, 255, 255),
                                                      fontSize: 12.0,
                                                    ),
                                                  ),
                                                  duration: Duration(milliseconds: 2000),
                                                ),
                                              );
                                              Navigator.pop(context);
                                            }
                                          },
                                          onSelectText: () {
                                            MixpanelManager().track('Chat Message Text Selected',
                                                properties: {'message': message.text});
                                            routeToPage(context, SelectTextScreen(message: message));
                                          },
                                          onShare: () {
                                            MixpanelManager()
                                                .track('Chat Message Shared', properties: {'message': message.text});
                                            Share.share(
                                              '${message.text.decodeString}\n\nResponse from Omi. Get yours at https://omi.me',
                                              subject: 'Chat with Omi',
                                            );
                                            Navigator.pop(context);
                                          },
                                          onReport: () {
                                            if (message.sender == MessageSender.human) {
                                              Navigator.pop(context);
                                              ScaffoldMessenger.of(context).showSnackBar(
                                                const SnackBar(
                                                  content: Text(
                                                    'You cannot report your own messages.',
                                                    style: TextStyle(
                                                      color: Color.fromARGB(255, 255, 255, 255),
                                                      fontSize: 12.0,
                                                    ),
                                                  ),
                                                  duration: Duration(milliseconds: 2000),
                                                ),
                                              );
                                              return;
                                            }
                                            showDialog(
                                              context: context,
                                              builder: (context) {
                                                return getDialog(
                                                  context,
                                                  () {
                                                    Navigator.of(context).pop();
                                                  },
                                                  () {
                                                    MixpanelManager().track('Chat Message Reported',
                                                        properties: {'message': message.text});
                                                    Navigator.of(context).pop();
                                                    Navigator.of(context).pop();
                                                    context.read<MessageProvider>().removeLocalMessage(message.id);
                                                    reportMessageServer(message.id);
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      const SnackBar(
                                                        content: Text(
                                                          'Message reported successfully.',
                                                          style: TextStyle(
                                                            color: Color.fromARGB(255, 255, 255, 255),
                                                            fontSize: 12.0,
                                                          ),
                                                        ),
                                                        duration: Duration(milliseconds: 2000),
                                                      ),
                                                    );
                                                  },
                                                  'Report Message',
                                                  'Are you sure you want to report this message?',
                                                );
                                              },
                                            );
                                          },
                                        ),
                                      );
                                    },
                                    child: Padding(
                                      key: ValueKey(message.id),
                                      padding:
                                          EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                                      child: message.sender == MessageSender.ai
                                          ? AIMessage(
                                              showTypingIndicator: provider.showTypingIndicator && chatIndex == 0,
                                              message: message,
                                              sendMessage: _sendMessageUtil,
                                              displayOptions: provider.messages.length <= 1 &&
                                                  provider.messageSenderApp(message.appId)?.isNotPersona() == true,
                                              appSender: provider.messageSenderApp(message.appId),
                                              updateConversation: (ServerConversation conversation) {
                                                context.read<ConversationProvider>().updateConversation(conversation);
                                              },
                                              setMessageNps: (int value) {
                                                provider.setMessageNps(message, value);
                                              },
                                            )
                                          : HumanMessage(message: message),
                                    ),
                                  );
                                },
                              ),
              ),
              Consumer<HomeProvider>(builder: (context, home, child) {
                bool shouldShowSuffixIcon(MessageProvider p) {
                  return !p.sendingMessage && _showSendButton;
                }

                bool shouldShowSendButton(MessageProvider p) {
                  return !p.sendingMessage && _showSendButton;
                }

                return Align(
                  alignment: Alignment.bottomCenter,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_isRecording) _buildRecordingOverlay(),
                      if (!_isRecording)
                        Container(
                          width: double.maxFinite,
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          margin: EdgeInsets.only(
                              left: 28,
                              right: 28,
                              bottom: widget.isPivotBottom ? 40 : (home.isChatFieldFocused ? 40 : 120)),
                          decoration: const BoxDecoration(
                            color: Colors.black,
                            borderRadius: BorderRadius.all(Radius.circular(16)),
                            border: GradientBoxBorder(
                              gradient: LinearGradient(colors: [
                                Color.fromARGB(127, 208, 208, 208),
                                Color.fromARGB(127, 188, 99, 121),
                                Color.fromARGB(127, 86, 101, 182),
                                Color.fromARGB(127, 126, 190, 236)
                              ]),
                              width: 1,
                            ),
                            shape: BoxShape.rectangle,
                          ),
                          child: Column(
                            children: [
                              Consumer<MessageProvider>(builder: (context, provider, child) {
                                if (provider.selectedFiles.isNotEmpty) {
                                  return Stack(
                                    children: [
                                      Align(
                                        alignment: Alignment.centerLeft,
                                        child: SizedBox(
                                          height: MediaQuery.sizeOf(context).height * 0.118,
                                          child: ListView.builder(
                                            itemCount: provider.selectedFiles.length,
                                            scrollDirection: Axis.horizontal,
                                            shrinkWrap: true,
                                            itemBuilder: (ctx, idx) {
                                              return Container(
                                                margin: const EdgeInsets.only(bottom: 10, top: 10, left: 10),
                                                height: MediaQuery.sizeOf(context).width * 0.2,
                                                width: MediaQuery.sizeOf(context).width * 0.2,
                                                decoration: BoxDecoration(
                                                  color: Colors.grey[800],
                                                  image: provider.selectedFileTypes[idx] == 'image'
                                                      ? DecorationImage(
                                                          image: FileImage(provider.selectedFiles[idx]),
                                                          fit: BoxFit.cover,
                                                        )
                                                      : null,
                                                  borderRadius: BorderRadius.circular(10),
                                                ),
                                                child: Stack(
                                                  children: [
                                                    provider.selectedFileTypes[idx] != 'image'
                                                        ? const Center(
                                                            child: Icon(
                                                              Icons.insert_drive_file,
                                                              color: Colors.white,
                                                              size: 30,
                                                            ),
                                                          )
                                                        : Container(),
                                                    if (provider.isFileUploading(provider.selectedFiles[idx].path))
                                                      Container(
                                                        color: Colors.black.withOpacity(0.5),
                                                        child: const Center(
                                                          child: SizedBox(
                                                            width: 20,
                                                            height: 20,
                                                            child: CircularProgressIndicator(
                                                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white70),
                                                            ),
                                                          ),
                                                        ),
                                                      ),
                                                    Positioned(
                                                      top: 4,
                                                      right: 4,
                                                      child: GestureDetector(
                                                        onTap: () {
                                                          provider.clearSelectedFile(idx);
                                                        },
                                                        child: CircleAvatar(
                                                          radius: 12,
                                                          backgroundColor: Colors.grey[700],
                                                          child: const Icon(Icons.close, size: 16, color: Colors.white),
                                                        ),
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              );
                                            },
                                          ),
                                        ),
                                      ),
                                    ],
                                  );
                                } else {
                                  return Container();
                                }
                              }),
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  IconButton(
                                    icon: Icon(
                                      Icons.add,
                                      color: provider.selectedFiles.length > 3 ? Colors.grey : const Color(0xFFF7F4F4),
                                      size: 24.0,
                                    ),
                                    onPressed: () {
                                      if (provider.selectedFiles.length > 3) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          const SnackBar(
                                            content: Text('You can only upload 4 files at a time'),
                                            duration: Duration(seconds: 2),
                                          ),
                                        );
                                        return;
                                      }
                                      showModalBottomSheet(
                                        context: context,
                                        backgroundColor: Colors.grey[850],
                                        shape: const RoundedRectangleBorder(
                                          borderRadius: BorderRadius.vertical(top: Radius.circular(16.0)),
                                        ),
                                        builder: (BuildContext context) {
                                          return Padding(
                                            padding: const EdgeInsets.fromLTRB(12, 12, 12, 40),
                                            child: Wrap(
                                              children: [
                                                ListTile(
                                                  leading: const Icon(Icons.camera_alt, color: Colors.white),
                                                  title:
                                                      const Text("Take a Photo", style: TextStyle(color: Colors.white)),
                                                  onTap: () {
                                                    Navigator.pop(context);
                                                    context.read<MessageProvider>().captureImage();
                                                  },
                                                ),
                                                ListTile(
                                                  leading: const Icon(Icons.photo, color: Colors.white),
                                                  title:
                                                      const Text("Select a Photo", style: TextStyle(color: Colors.white)),
                                                  onTap: () {
                                                    Navigator.pop(context);
                                                    context.read<MessageProvider>().selectImage();
                                                  },
                                                ),
                                                ListTile(
                                                  leading: const Icon(Icons.insert_drive_file, color: Colors.white),
                                                  title:
                                                      const Text("Select a File", style: TextStyle(color: Colors.white)),
                                                  onTap: () {
                                                    Navigator.pop(context);
                                                    context.read<MessageProvider>().selectFile();
                                                  },
                                                ),
                                              ],
                                            ),
                                          );
                                        },
                                      );
                                    },
                                  ),
                                  Expanded(
                                    child: ConstrainedBox(
                                      constraints: const BoxConstraints(
                                        maxHeight: 150,
                                      ),
                                      child: TextField(
                                        enabled: true,
                                        controller: textController,
                                        obscureText: false,
                                        onChanged: (value) {
                                          setShowSendButton();
                                        },
                                        focusNode: home.chatFieldFocusNode,
                                        textAlign: TextAlign.start,
                                        textAlignVertical: TextAlignVertical.top,
                                        decoration: const InputDecoration(
                                          hintText: 'Message',
                                          hintStyle: TextStyle(fontSize: 14.0, color: Colors.grey),
                                          focusedBorder: InputBorder.none,
                                          enabledBorder: InputBorder.none,
                                          contentPadding: EdgeInsets.only(top: 8, bottom: 10),
                                        ),
                                        maxLines: null,
                                        keyboardType: TextInputType.multiline,
                                        style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200, height: 24 / 14),
                                      ),
                                    ),
                                  ),
                                  IconButton(
                                    splashColor: Colors.transparent,
                                    splashRadius: 1,
                                    onPressed: () => _toggleVoiceRecording(),
                                    icon: Icon(
                                      _isRecording ? Icons.stop : Icons.mic,
                                      color: _isRecording ? Colors.red : const Color(0xFFF7F4F4),
                                      size: 20.0,
                                    ),
                                  ),
                                  !shouldShowSuffixIcon(provider) && !shouldShowSendButton(provider)
                                      ? const SizedBox.shrink()
                                      : IconButton(
                                          splashColor: Colors.transparent,
                                          splashRadius: 1,
                                          onPressed: provider.sendingMessage || provider.isUploadingFiles
                                              ? null
                                              : () {
                                                  String message = textController.text;
                                                  if (message.isEmpty) return;
                                                  if (connectivityProvider.isConnected) {
                                                    _sendMessageUtil(message);
                                                  } else {
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      const SnackBar(
                                                        content:
                                                            Text('Please check your internet connection and try again'),
                                                        duration: Duration(seconds: 2),
                                                      ),
                                                    );
                                                  }
                                                },
                                          icon: const Icon(
                                            Icons.arrow_upward_outlined,
                                            color: Color(0xFFF7F4F4),
                                            size: 20.0,
                                          ),
                                        ),
                                ],
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                );
              }),
            ],
          ),
        );
      },
    );
  }

  _sendMessageUtil(String text) {
    var provider = context.read<MessageProvider>();
    MixpanelManager().chatMessageSent(text);
    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    scrollToBottom();
    textController.clear();
    provider.sendMessageStreamToServer(text);
    provider.clearSelectedFiles();
    provider.setSendingMessage(false);
  }

  sendInitialAppMessage(App? app) async {
    context.read<MessageProvider>().setSendingMessage(true);
    scrollToBottom();
    ServerMessage message = await getInitialAppMessage(app?.id);
    if (mounted) {
      context.read<MessageProvider>().addMessage(message);
    }
    scrollToBottom();
    context.read<MessageProvider>().setSendingMessage(false);
  }

  void _moveListToBottom() {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (scrollController.hasClients) {
        scrollController.animateTo(
          0.0,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  scrollToBottom() => _moveListToBottom();

  Future<void> _toggleVoiceRecording() async {
    if (!_isListening) {
      bool available = await _speech.initialize();
      if (available) {
        // Hide the navigation bar when starting recording
        context.read<HomeProvider>().chatFieldFocusNode.requestFocus();
        
        setState(() {
          _isListening = true;
          _isRecording = true;
          _recognizedText = '';
          _recordingDuration = 0;
          _currentSoundLevel = 0;
        });
        
        _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
          setState(() {
            _recordingDuration++;
          });
        });
        
        _speech.listen(
          onResult: (result) {
            setState(() {
              _recognizedText = result.recognizedWords;
            });
          },
          onSoundLevelChange: (level) {
            setState(() {
              // Scale the sound level to be more visible
              _currentSoundLevel = level * 2;
            });
          },
          listenFor: const Duration(minutes: 5),
          partialResults: true,
          listenMode: stt.ListenMode.deviceDefault,
          cancelOnError: false,
        );
      }
    } else {
      _speech.stop();
      _recordingTimer?.cancel();
      
      // Show the navigation bar when stopping recording
      context.read<HomeProvider>().chatFieldFocusNode.unfocus();
      
      setState(() {
        _isListening = false;
        _isRecording = false;
        _recordingDuration = 0;
        _currentSoundLevel = 0;
        if (_recognizedText.isNotEmpty) {
          textController.text = _recognizedText;
          setShowSendButton();
        }
      });
    }
  }
}

class WaveformPainter extends CustomPainter {
  final double soundLevel;
  static final Queue<double> waveHistory = Queue<double>();
  static const int maxPoints = 50;
  static final _random = Random();
  static bool _initialized = false;

  WaveformPainter({this.soundLevel = 0}) {
    // Initialize queue only once
    if (!_initialized) {
      for (int i = 0; i < maxPoints; i++) {
        waveHistory.add(2.0);
      }
      _initialized = true;
    }
    
    // Update wave history with new sound level
    if (soundLevel > 0) {
      waveHistory.removeFirst();
      waveHistory.addLast(soundLevel.clamp(2.0, 40.0));
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final centerY = height / 2;
    
    // Draw waveform bars
    final barWidth = (width / maxPoints).floor();
    int i = 0;
    
    for (final level in waveHistory) {
      final x = i * barWidth.toDouble();
      
      // Add some randomness for natural movement
      final jitter = _random.nextDouble() * 2.0;
      final amplitude = (level + jitter).clamp(2.0, height / 2);
      
      canvas.drawLine(
        Offset(x, centerY - amplitude),
        Offset(x, centerY + amplitude),
        paint,
      );
      
      i++;
    }
  }

  @override
  bool shouldRepaint(covariant WaveformPainter oldDelegate) => 
    oldDelegate.soundLevel != soundLevel;
}
