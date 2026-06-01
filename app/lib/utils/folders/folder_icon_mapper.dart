import 'package:flutter/widgets.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

/// Maps folder icon strings (emojis) to FontAwesome IconData.
/// Falls back to a folder icon for unknown values.
FaIconData folderIconToFa(String? iconString) {
  return _emojiToFaMap[iconString] ?? FontAwesomeIcons.folder;
}

/// Mapping from emoji strings to FontAwesome icons.
const Map<String, FaIconData> _emojiToFaMap = {
  '📁': FontAwesomeIcons.solidFolder,
  '💼': FontAwesomeIcons.briefcase,
  '🏠': FontAwesomeIcons.solidHouse,
  '📚': FontAwesomeIcons.book,
  '👨‍👩‍👧‍👦': FontAwesomeIcons.users,
  '👤': FontAwesomeIcons.solidHeart,
  '👥': FontAwesomeIcons.users,
  '❤️': FontAwesomeIcons.solidHeart,
  '🎮': FontAwesomeIcons.gamepad,
  '✈️': FontAwesomeIcons.plane,
  '🏥': FontAwesomeIcons.solidHospital,
  '🛒': FontAwesomeIcons.cartShopping,
  '💰': FontAwesomeIcons.moneyBill,
  '🎵': FontAwesomeIcons.music,
  '🎨': FontAwesomeIcons.palette,
  '📝': FontAwesomeIcons.pen,
  '💬': FontAwesomeIcons.solidComments,
  '🌎': FontAwesomeIcons.globe,
  '🛠️': FontAwesomeIcons.screwdriverWrench,
  '🍔': FontAwesomeIcons.burger,
  '🏆': FontAwesomeIcons.trophy,
  '🔒': FontAwesomeIcons.lock,
  '⭐': FontAwesomeIcons.solidStar,
  '🕐': FontAwesomeIcons.solidClock,
  '📊': FontAwesomeIcons.chartSimple,
};

/// List of all available folder icon strings (for use in icon picker UI).
const List<String> folderIconStrings = [
  '📁',
  '💼',
  '🏠',
  '📚',
  '👨‍👩‍👧‍👦',
  '❤️',
  '🎮',
  '✈️',
  '🏥',
  '🛒',
  '💰',
  '🎵',
  '🎨',
  '📝',
  '💬',
  '🌎',
  '🛠️',
  '🍔',
  '🏆',
  '🔒',
];
