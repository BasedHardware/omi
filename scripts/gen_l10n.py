#!/usr/bin/env python3
"""
Generate localization .dart files from .arb files.
This script mimics the functionality of flutter gen-l10n.
"""

import json
import os
from pathlib import Path

def load_arb_file(file_path):
    """Load an .arb file and return its contents."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_locale_from_file(file_path):
    """Extract locale code from filename (e.g., app_en.arb -> en)."""
    name = Path(file_path).stem
    return name.replace('app_', '')

def should_skip_key(key):
    """Check if a key should be skipped (like @@locale)."""
    return key.startswith('@@')

def escape_dart_string(s):
    """Escape a string for Dart."""
    s = s.replace('\\', '\\\\')
    s = s.replace("'", "\\'")
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s

def generate_dart_file(locale, arb_data, template_data, output_file):
    """Generate a localization .dart file from .arb data."""
    
    locale_name = locale.upper() if locale else 'EN'
    class_name = f"AppLocalizations{locale_name}"
    
    # Generate the class
    lines = [
        "// ignore: unused_import",
        "import 'package:intl/intl.dart' as intl;",
        "import 'app_localizations.dart';",
        "",
        "// ignore_for_file: type=lint",
        "",
        f"/// The translations for {get_language_name(locale)} (`{locale}`).",
        f"class {class_name} extends AppLocalizations {{",
        f"  {class_name}([String locale = '{locale}']) : super(locale);",
        "",
    ]
    
    # Add getters for each translation key
    for key in sorted(template_data.keys()):
        if should_skip_key(key):
            continue
        
        # Only include keys that are present in this locale's .arb file
        # For non-English locales, skip keys that are only in English
        if key not in arb_data:
            if locale != 'en':
                # Skip untranslated keys in non-English locales
                continue
            else:
                # For English, use the value from template_data
                value = template_data[key]
        else:
            value = arb_data[key]
        
        # Handle plurals and other special formatting
        if isinstance(value, str):
            # Escape the value for Dart
            escaped_value = escape_dart_string(value)
            
            # Generate the getter
            if len(escaped_value) > 60 or '\n' in value:
                lines.append(f"  @override")
                lines.append(f"  String get {key} =>")
                lines.append(f"      '{escaped_value}';")
                lines.append("")
            else:
                lines.append(f"  @override")
                lines.append(f"  String get {key} => '{escaped_value}';")
                lines.append("")
    
    lines.append("}")
    
    # Write the file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def get_language_name(locale):
    """Get the English name of a language from its locale code."""
    languages = {
        'en': 'English',
        'ar': 'Arabic',
        'bg': 'Bulgarian',
        'ca': 'Catalan',
        'cs': 'Czech',
        'da': 'Danish',
        'de': 'German',
        'el': 'Greek',
        'es': 'Spanish',
        'et': 'Estonian',
        'fi': 'Finnish',
        'fr': 'French',
        'hi': 'Hindi',
        'hu': 'Hungarian',
        'id': 'Indonesian',
        'it': 'Italian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'lt': 'Lithuanian',
        'lv': 'Latvian',
        'ms': 'Malay',
        'nl': 'Dutch',
        'no': 'Norwegian',
        'pl': 'Polish',
        'pt': 'Portuguese',
        'ro': 'Romanian',
        'ru': 'Russian',
        'sk': 'Slovak',
        'sv': 'Swedish',
        'th': 'Thai',
        'tr': 'Turkish',
        'uk': 'Ukrainian',
        'vi': 'Vietnamese',
        'zh': 'Chinese',
    }
    return languages.get(locale, locale.upper())

def main():
    """Main function."""
    app_dir = Path('/workspaces/omi/app')
    l10n_dir = app_dir / 'lib' / 'l10n'
    
    # Load the English template
    template_file = l10n_dir / 'app_en.arb'
    template_data = load_arb_file(template_file)
    
    # Generate .dart files for each locale
    arb_files = sorted(l10n_dir.glob('app_*.arb'))
    
    for arb_file in arb_files:
        locale = get_locale_from_file(arb_file)
        print(f"Generating {locale}...")
        
        arb_data = load_arb_file(arb_file)
        
        # Generate the output file name
        output_file = l10n_dir / f'app_localizations_{locale}.dart'
        
        generate_dart_file(locale, arb_data, template_data, output_file)
        print(f"  -> {output_file.name}")
    
    print("Done!")

if __name__ == '__main__':
    main()
