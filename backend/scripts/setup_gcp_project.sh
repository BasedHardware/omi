#!/bin/bash
# Setup script for Omi/Nooto Backend on GCP
# This script sets up a complete GCP project with all required services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Omi/Nooto GCP Project Setup${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if firebase is installed
if ! command -v firebase &> /dev/null; then
    echo -e "${RED}Error: firebase CLI is not installed${NC}"
    echo "Please install it with: npm install -g firebase-tools"
    exit 1
fi

# Prompt for project details
read -p "Enter GCP Project ID (e.g., nooto-prod): " PROJECT_ID
read -p "Enter Project Name (e.g., Nooto Production): " PROJECT_NAME
read -p "Enter Billing Account ID (or press Enter to skip): " BILLING_ACCOUNT
read -p "Enter GCP Region (default: us-central1): " REGION
REGION=${REGION:-us-central1}

echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Project ID: $PROJECT_ID"
echo "  Project Name: $PROJECT_NAME"
echo "  Region: $REGION"
echo "  Billing Account: ${BILLING_ACCOUNT:-Not set}"
echo ""
read -p "Continue with this configuration? (y/n): " CONFIRM

if [[ $CONFIRM != "y" && $CONFIRM != "Y" ]]; then
    echo "Setup cancelled."
    exit 0
fi

echo ""
echo -e "${GREEN}Step 1: Creating GCP Project${NC}"

# Check if project exists
if gcloud projects describe $PROJECT_ID &> /dev/null; then
    echo -e "${YELLOW}Project $PROJECT_ID already exists. Using existing project.${NC}"
else
    echo "Creating project $PROJECT_ID..."
    gcloud projects create $PROJECT_ID --name="$PROJECT_NAME"
    echo -e "${GREEN}✓ Project created${NC}"
fi

# Set default project
gcloud config set project $PROJECT_ID

# Link billing account if provided
if [[ -n "$BILLING_ACCOUNT" ]]; then
    echo ""
    echo -e "${GREEN}Step 2: Linking Billing Account${NC}"
    gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT
    echo -e "${GREEN}✓ Billing linked${NC}"
else
    echo ""
    echo -e "${YELLOW}Step 2: Skipping billing (no billing account provided)${NC}"
    echo -e "${YELLOW}You'll need to enable billing manually before creating resources${NC}"
fi

echo ""
echo -e "${GREEN}Step 3: Enabling Required APIs${NC}"
echo "This may take a few minutes..."

APIS=(
    "firestore.googleapis.com"
    "firebase.googleapis.com"
    "storage-api.googleapis.com"
    "storage.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "serviceusage.googleapis.com"
    "iam.googleapis.com"
)

for API in "${APIS[@]}"; do
    echo "  Enabling $API..."
    gcloud services enable $API --project=$PROJECT_ID
done

echo -e "${GREEN}✓ All APIs enabled${NC}"

echo ""
echo -e "${GREEN}Step 4: Creating Firestore Database${NC}"

# Check if Firestore database exists
if gcloud firestore databases describe --database="(default)" --project=$PROJECT_ID &> /dev/null; then
    echo -e "${YELLOW}Firestore database already exists${NC}"
else
    echo "Creating Firestore database in $REGION..."
    gcloud firestore databases create --location=$REGION --type=firestore-native --project=$PROJECT_ID
    echo -e "${GREEN}✓ Firestore database created${NC}"
fi

echo ""
echo -e "${GREEN}Step 5: Creating GCS Buckets${NC}"

BUCKETS=(
    "$PROJECT_ID-speech-profiles"
    "$PROJECT_ID-backups"
    "$PROJECT_ID-plugins-logos"
    "$PROJECT_ID-memories-recordings"
    "$PROJECT_ID-postprocessing"
    "$PROJECT_ID-private-cloud-sync"
    "$PROJECT_ID-temporal-sync"
    "$PROJECT_ID-app-thumbnails"
    "$PROJECT_ID-chat-files"
)

for BUCKET in "${BUCKETS[@]}"; do
    if gcloud storage buckets describe gs://$BUCKET --project=$PROJECT_ID &> /dev/null; then
        echo -e "${YELLOW}  Bucket $BUCKET already exists${NC}"
    else
        echo "  Creating bucket: $BUCKET..."
        gcloud storage buckets create gs://$BUCKET \
            --project=$PROJECT_ID \
            --location=$REGION \
            --uniform-bucket-level-access
        echo -e "${GREEN}  ✓ Bucket created: $BUCKET${NC}"
    fi
done

echo -e "${GREEN}✓ All buckets created${NC}"

echo ""
echo -e "${GREEN}Step 6: Creating Service Account${NC}"

SERVICE_ACCOUNT_NAME="coolify-backend"
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Check if service account exists
if gcloud iam service-accounts describe $SERVICE_ACCOUNT_EMAIL --project=$PROJECT_ID &> /dev/null; then
    echo -e "${YELLOW}Service account already exists${NC}"
else
    echo "Creating service account: $SERVICE_ACCOUNT_NAME..."
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Coolify Backend Service Account" \
        --project=$PROJECT_ID
    echo -e "${GREEN}✓ Service account created${NC}"
fi

echo ""
echo -e "${GREEN}Step 7: Granting IAM Roles${NC}"

ROLES=(
    "roles/datastore.user"
    "roles/firebase.admin"
    "roles/storage.objectAdmin"
)

for ROLE in "${ROLES[@]}"; do
    echo "  Granting $ROLE..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$ROLE" \
        --condition=None \
        > /dev/null
done

echo -e "${GREEN}✓ IAM roles granted${NC}"

echo ""
echo -e "${GREEN}Step 8: Creating Service Account Key${NC}"

KEY_FILE="$PROJECT_ID-service-account-key.json"

if [[ -f "$KEY_FILE" ]]; then
    echo -e "${YELLOW}Key file already exists: $KEY_FILE${NC}"
    read -p "Overwrite? (y/n): " OVERWRITE
    if [[ $OVERWRITE != "y" && $OVERWRITE != "Y" ]]; then
        echo "Skipping key creation"
    else
        gcloud iam service-accounts keys create $KEY_FILE \
            --iam-account=$SERVICE_ACCOUNT_EMAIL \
            --project=$PROJECT_ID
        echo -e "${GREEN}✓ Service account key created: $KEY_FILE${NC}"
    fi
else
    gcloud iam service-accounts keys create $KEY_FILE \
        --iam-account=$SERVICE_ACCOUNT_EMAIL \
        --project=$PROJECT_ID
    echo -e "${GREEN}✓ Service account key created: $KEY_FILE${NC}"
fi

echo ""
echo -e "${GREEN}Step 9: Deploying Firestore Indexes${NC}"

# Check if firestore.indexes.json exists
if [[ ! -f "firestore.indexes.json" ]]; then
    echo -e "${YELLOW}No firestore.indexes.json found. Skipping index deployment.${NC}"
    echo "If you have indexes from another project, export them first:"
    echo "  firebase --project=source-project firestore:indexes > firestore.indexes.json"
else
    echo "Deploying Firestore indexes..."
    firebase --project=$PROJECT_ID deploy --only firestore:indexes
    echo -e "${GREEN}✓ Firestore indexes deployed${NC}"
fi

echo ""
echo -e "${GREEN}Step 10: Generating Environment Variables${NC}"

ENV_FILE=".env.$PROJECT_ID"

cat > $ENV_FILE << EOF
# Generated GCP Environment Variables for $PROJECT_ID
# Created: $(date)

# Google Cloud Project
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GCP_PROJECT_ID=$PROJECT_ID

# Service Account JSON (minify this for Coolify)
# Copy the contents of: $KEY_FILE
SERVICE_ACCOUNT_JSON=\$(cat $KEY_FILE | jq -c .)

# Google Cloud Storage Buckets
BUCKET_SPEECH_PROFILES=$PROJECT_ID-speech-profiles
BUCKET_BACKUPS=$PROJECT_ID-backups
BUCKET_PLUGINS_LOGOS=$PROJECT_ID-plugins-logos
BUCKET_MEMORIES_RECORDINGS=$PROJECT_ID-memories-recordings
BUCKET_POSTPROCESSING=$PROJECT_ID-postprocessing
BUCKET_PRIVATE_CLOUD_SYNC=$PROJECT_ID-private-cloud-sync
BUCKET_TEMPORAL_SYNC_LOCAL=$PROJECT_ID-temporal-sync
BUCKET_APP_THUMBNAILS=$PROJECT_ID-app-thumbnails
BUCKET_CHAT_FILES=$PROJECT_ID-chat-files

# Add your API keys and other configuration below:
# BASE_API_URL=https://your-domain.com
# ADMIN_KEY=your-admin-key
# OPENAI_API_KEY=sk-proj-...
# DEEPGRAM_API_KEY=...
# PINECONE_API_KEY=...
# PINECONE_INDEX_NAME=...
EOF

echo -e "${GREEN}✓ Environment variables written to: $ENV_FILE${NC}"

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Setup Complete! 🎉${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Service Account Key:"
echo "   Location: $KEY_FILE"
echo "   Copy the minified JSON to Coolify as SERVICE_ACCOUNT_JSON"
echo ""
echo "2. Environment Variables:"
echo "   Location: $ENV_FILE"
echo "   Copy all variables to your Coolify deployment"
echo ""
echo "3. Firebase Console:"
echo "   https://console.firebase.google.com/project/$PROJECT_ID"
echo "   Add your iOS/Android apps and download config files"
echo ""
echo "4. GCP Console:"
echo "   https://console.cloud.google.com/home/dashboard?project=$PROJECT_ID"
echo ""
echo "5. To minify the service account JSON for Coolify:"
echo "   cat $KEY_FILE | jq -c ."
echo ""
echo -e "${GREEN}Resources Created:${NC}"
echo "  ✓ GCP Project: $PROJECT_ID"
echo "  ✓ Firestore Database (region: $REGION)"
echo "  ✓ 9 GCS Buckets"
echo "  ✓ Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "  ✓ Service Account Key: $KEY_FILE"
echo "  ✓ IAM Roles: datastore.user, firebase.admin, storage.objectAdmin"
if [[ -f "firestore.indexes.json" ]]; then
    echo "  ✓ Firestore Indexes Deployed"
fi
echo ""
