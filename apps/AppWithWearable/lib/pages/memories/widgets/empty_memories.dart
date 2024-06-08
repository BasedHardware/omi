import 'package:flutter/material.dart';

class EmptyMemoriesWidget extends StatefulWidget {
  const EmptyMemoriesWidget({super.key});

  @override
  State<EmptyMemoriesWidget> createState() => _EmptyMemoriesWidgetState();
}

class _EmptyMemoriesWidgetState extends State<EmptyMemoriesWidget> {
  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.max,
      children: [
        const SizedBox(height: 16),
        ClipRRect(
          borderRadius: BorderRadius.circular(8.0),
          child: Image.asset(
            'assets/images/logo0.png',
            width: 72.0,
            height: 72.0,
            fit: BoxFit.cover,
          ),
        ),
        const SizedBox(height: 16),
        Container(
          width: double.maxFinite,
          constraints: const BoxConstraints(
            maxWidth: 300.0,
          ),
          decoration: BoxDecoration(
            color: const Color(0x34F7F4F4),
            borderRadius: BorderRadius.circular(12.0),
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 12.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const SizedBox(height: 8),
                Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF515253),
                    borderRadius: BorderRadius.circular(24.0),
                  ),
                  child: Padding(
                    padding: const EdgeInsetsDirectional.symmetric(vertical: 4, horizontal: 12),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.max,
                          children: [
                            Icon(
                              Icons.blur_on,
                              color: Theme.of(context).secondaryHeaderColor,
                              size: 24.0,
                            ),
                            const SizedBox(
                              width: 8,
                            ),
                            const Text(
                              'Friend',
                              style: TextStyle(
                                // color: FlutterFlowTheme.of(context).secondary,
                                fontWeight: FontWeight.w500,
                                // STYLE ME
                                // useGoogleFonts:
                                //     GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).labelMediumFamily),
                              ),
                            ),
                            const SizedBox(width: 4),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const Padding(
                  padding: EdgeInsetsDirectional.fromSTEB(4.0, 4.0, 0.0, 8.0),
                  child: Text(
                    'Your most important memories will be stored here. Try Recording or Adding your first Memory!',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      // fontFamily: FlutterFlowTheme.of(context).labelMediumFamily,
                      // color: FlutterFlowTheme.of(context).secondary,
                      fontWeight: FontWeight.bold,
                      // useGoogleFonts:
                      //     GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).labelMediumFamily),
                      height: 1.5, // STYLE ME
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
