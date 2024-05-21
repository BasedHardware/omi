import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/memories/page.dart';

class BottomNavWrapper extends StatefulWidget {
  final dynamic btDevice;

  const BottomNavWrapper({super.key, this.btDevice});

  @override
  State<BottomNavWrapper> createState() => _BottomNavWrapperState();
}

class _BottomNavWrapperState extends State<BottomNavWrapper> {
  int _selectedIndex = 1;
  List<Widget> screens = [Container(), const SizedBox(), const SizedBox()];
  List<MemoryRecord> memories = [];

  _initiateMemories() async {
    memories = await MemoryStorage.getAllMemories(filterOutUseless: true);
    setState(() {});
  }

  @override
  void initState() {
    // _refreshMemories();
    _initiateMemories();
    super.initState();
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
            HomePage(btDevice: widget.btDevice, refreshMemories: _initiateMemories),
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
        actions: [],
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
}
