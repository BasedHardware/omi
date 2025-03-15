#!/bin/bash

# Script to fix zsh prompt issues with cursor resets and multiple prompts
# Created to address issues with Powerlevel10k configuration

echo "ZSH Prompt Fix Utility"
echo "======================"
echo

# Backup existing configuration
echo "Creating backup of your current p10k configuration..."
cp ~/.p10k.zsh ~/.p10k.zsh.backup.$(date +%Y%m%d%H%M%S)
echo "Backup created at ~/.p10k.zsh.backup.$(date +%Y%m%d%H%M%S)"
echo

# Check for common issues in p10k configuration
echo "Checking for common issues in your p10k configuration..."

# Fix 1: Ensure proper prompt length calculation
if grep -q "typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_VIINS_CONTENT_EXPANSION=" ~/.p10k.zsh; then
  sed -i.bak 's/typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_VIINS_CONTENT_EXPANSION=.*/typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_VIINS_CONTENT_EXPANSION='\''❯'\''/' ~/.p10k.zsh
  echo "✓ Fixed prompt character configuration"
else
  echo "! Could not find prompt character configuration"
fi

# Fix 2: Ensure proper segment termination
if grep -q "typeset -g POWERLEVEL9K_RIGHT_PROMPT_LAST_SEGMENT_END_SYMBOL=" ~/.p10k.zsh; then
  sed -i.bak 's/typeset -g POWERLEVEL9K_RIGHT_PROMPT_LAST_SEGMENT_END_SYMBOL=.*/typeset -g POWERLEVEL9K_RIGHT_PROMPT_LAST_SEGMENT_END_SYMBOL='\'''\''/' ~/.p10k.zsh
  echo "✓ Fixed right prompt last segment end symbol"
else
  echo "! Could not find right prompt last segment end symbol configuration"
fi

# Fix 3: Add proper prompt length calculation
echo "Adding proper prompt length calculation..."
cat >> ~/.p10k.zsh << 'EOL'

# Fix for cursor reset issues
typeset -g POWERLEVEL9K_RIGHT_PROMPT_LAST_SEGMENT_END_SYMBOL=''
typeset -g POWERLEVEL9K_PROMPT_ON_NEWLINE=false
typeset -g POWERLEVEL9K_RPROMPT_ON_NEWLINE=false
typeset -g POWERLEVEL9K_MULTILINE_FIRST_PROMPT_PREFIX=''
typeset -g POWERLEVEL9K_MULTILINE_LAST_PROMPT_PREFIX=''
EOL
echo "✓ Added proper prompt length calculation"

# Fix 4: Check for custom segments that might be causing issues
if grep -q "backend" ~/.zshrc; then
  echo "! Found 'backend' reference in your .zshrc file. This might be causing the issue."
  echo "  Consider removing or fixing any custom segments that add 'backend' to your prompt."
fi

echo
echo "Fixes applied. Please restart your terminal or run 'source ~/.zshrc' to apply changes."
echo "If issues persist, you can restore your backup with:"
echo "cp ~/.p10k.zsh.backup.$(date +%Y%m%d%H%M%S) ~/.p10k.zsh && source ~/.zshrc"
echo
echo "For a more thorough fix, consider running 'p10k configure' in a larger terminal window."
