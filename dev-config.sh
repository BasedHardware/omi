#!/bin/bash
# Central configuration for development environment

# Set your ngrok base URL here (only edit this one place)
export NGROK_BASE_URL="https://opossum-cuddly-ultimately.ngrok-free.app/"

# Get timestamp for backup files
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="env_backups"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Backup app environment file if it exists
if [ -f app/.dev.env ]; then
  cp app/.dev.env "$BACKUP_DIR/app_dev_env_$TIMESTAMP.bak"
  echo "📦 Backed up app/.dev.env to $BACKUP_DIR/app_dev_env_$TIMESTAMP.bak"
fi

# Update app environment file
echo "API_BASE_URL=$NGROK_BASE_URL" > app/.dev.env
echo "✅ Updated app/.dev.env with API_BASE_URL=$NGROK_BASE_URL"

# Backup and update backend environment file (preserve other variables)
if [ -f backend/.dev.env ]; then
  # Backup before modifying
  cp backend/.dev.env "$BACKUP_DIR/backend_dev_env_$TIMESTAMP.bak"
  echo "📦 Backed up backend/.dev.env to $BACKUP_DIR/backend_dev_env_$TIMESTAMP.bak"

  # Update existing backend env file, replacing API_BASE_URL line
  sed -i.bak "s|^API_BASE_URL=.*|API_BASE_URL=$NGROK_BASE_URL|g" backend/.dev.env
  echo "✅ Updated backend/.dev.env with API_BASE_URL=$NGROK_BASE_URL"
elif [ -f backend/.env ]; then
  # Backup before modifying
  cp backend/.env "$BACKUP_DIR/backend_env_$TIMESTAMP.bak"
  echo "📦 Backed up backend/.env to $BACKUP_DIR/backend_env_$TIMESTAMP.bak"

  # Update existing backend env file, replacing API_BASE_URL line
  sed -i.bak "s|^API_BASE_URL=.*|API_BASE_URL=$NGROK_BASE_URL|g" backend/.env
  echo "✅ Updated backend/.env with API_BASE_URL=$NGROK_BASE_URL"
else
  echo "⚠️ No backend environment file found. Create one first."
fi

# Also update BASE_API_URL if present (for services that call back to your backend)
if grep -q "^BASE_API_URL=" backend/.dev.env 2>/dev/null; then
  sed -i.bak "s|^BASE_API_URL=.*|BASE_API_URL=$NGROK_BASE_URL|g" backend/.dev.env
  echo "✅ Updated backend/.dev.env with BASE_API_URL=$NGROK_BASE_URL"
elif grep -q "^BASE_API_URL=" backend/.env 2>/dev/null; then
  sed -i.bak "s|^BASE_API_URL=.*|BASE_API_URL=$NGROK_BASE_URL|g" backend/.env
  echo "✅ Updated backend/.env with BASE_API_URL=$NGROK_BASE_URL"
fi

# Clean up temporary .bak files created by sed
if [ -f backend/.env.bak ]; then
  rm backend/.env.bak
fi
if [ -f backend/.dev.env.bak ]; then
  rm backend/.dev.env.bak
fi

# Print next steps
echo ""
echo "🚀 Configuration updated!"
echo "🔄 Previous configurations backed up in $BACKUP_DIR/"
echo ""
echo "Next steps:"
echo "1. Start ngrok: ngrok http --domain=${NGROK_BASE_URL%/} 8000"
echo "2. Start backend: cd backend && source venv/bin/activate && uvicorn main:app --reload --env-file .dev.env"
echo "3. Run your app"