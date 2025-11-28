# GCP Project Setup Script

This script automates the complete setup of a GCP project for Omi/Nooto backend deployment.

## What It Does

The script automates these steps:

1. **Creates GCP Project** (or uses existing)
2. **Links Billing Account** (optional)
3. **Enables Required APIs**:
   - Firestore
   - Firebase
   - Cloud Storage
   - IAM
   - Cloud Resource Manager
4. **Creates Firestore Database** (Native mode)
5. **Creates GCS Buckets**:
   - speech-profiles
   - backups
   - plugins-logos
   - memories-recordings
   - postprocessing
   - private-cloud-sync
   - temporal-sync
   - app-thumbnails
   - chat-files
6. **Creates Service Account** with proper IAM roles
7. **Generates Service Account Key** (JSON)
8. **Deploys Firestore Indexes** (if firestore.indexes.json exists)
9. **Generates `.env` File** with all required variables

## Prerequisites

### Required Tools

```bash
# Install gcloud CLI
# https://cloud.google.com/sdk/docs/install

# Install Firebase CLI
npm install -g firebase-tools

# Install jq (for JSON minification)
brew install jq  # macOS
# or
apt-get install jq  # Ubuntu/Debian
```

### Authentication

```bash
# Login to gcloud
gcloud auth login

# Login to Firebase
firebase login
```

## Usage

### Basic Usage

```bash
cd backend/scripts
./setup_gcp_project.sh
```

The script will prompt you for:
- **Project ID** (e.g., `nooto-prod`)
- **Project Name** (e.g., `Nooto Production`)
- **Billing Account ID** (optional, find at https://console.cloud.google.com/billing)
- **GCP Region** (default: `us-central1`)

### Example Session

```
Enter GCP Project ID (e.g., nooto-prod): nooto-prod
Enter Project Name (e.g., Nooto Production): Nooto Production
Enter Billing Account ID (or press Enter to skip): 018947-0443A9-7919B7
Enter GCP Region (default: us-central1): us-central1

Configuration:
  Project ID: nooto-prod
  Project Name: Nooto Production
  Region: us-central1
  Billing Account: 018947-0443A9-7919B7

Continue with this configuration? (y/n): y
```

## After Running the Script

### 1. Copy Service Account Key to Coolify

The script creates a file like `nooto-prod-service-account-key.json`. You need to minify it and add to Coolify:

```bash
# Minify the JSON
cat nooto-prod-service-account-key.json | jq -c .

# Copy the output and paste it into Coolify as:
# SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

### 2. Add Environment Variables to Coolify

The script creates a `.env.nooto-prod` file. Copy all variables to your Coolify deployment:

```bash
cat .env.nooto-prod
```

Add these to Coolify:
- `GOOGLE_CLOUD_PROJECT`
- `SERVICE_ACCOUNT_JSON`
- `BUCKET_SPEECH_PROFILES`
- `BUCKET_BACKUPS`
- `BUCKET_PLUGINS_LOGOS`
- etc.

### 3. Set Up Firebase Apps

Go to Firebase Console and add your iOS/Android apps:

1. Visit: https://console.firebase.google.com/project/YOUR_PROJECT_ID
2. Click "Add app" → iOS
   - Bundle ID: `com.togodynamics.nooto` (or your bundle ID)
   - Download `GoogleService-Info.plist`
   - Place in: `app/ios/Config/Prod/`
3. Click "Add app" → Android
   - Package name: `com.togodynamics.nooto`
   - Download `google-services.json`
   - Place in: `app/android/app/src/prod/`

### 4. Deploy to Coolify

In Coolify:
1. Add all environment variables from `.env.YOUR_PROJECT_ID`
2. Redeploy the service
3. Test the deployment

## Firestore Indexes

If you have an existing project with indexes, export them first:

```bash
# Export from existing project
firebase --project=nooto-dev firestore:indexes > firestore.indexes.json

# Then run the setup script (it will deploy these indexes)
./setup_gcp_project.sh
```

If you don't have indexes yet, the script will skip this step. You can deploy them later:

```bash
firebase --project=YOUR_PROJECT_ID deploy --only firestore:indexes
```

## Files Created

After running the script, you'll have:

- `YOUR_PROJECT_ID-service-account-key.json` - Service account credentials (keep secure!)
- `.env.YOUR_PROJECT_ID` - Environment variables for Coolify
- `firestore.indexes.json` - Firestore indexes (if exported from another project)
- `firebase.json` - Firebase configuration

## Security Notes

⚠️ **IMPORTANT**: The service account key file contains sensitive credentials!

- ❌ **DO NOT** commit `*-service-account-key.json` to git
- ❌ **DO NOT** share this file publicly
- ✅ **DO** store it securely (password manager, secrets manager)
- ✅ **DO** add `*-service-account-key.json` to `.gitignore`

## Troubleshooting

### Billing Not Enabled

```
ERROR: The billing account for the owning project is disabled
```

**Solution**: Run the script again and provide your billing account ID, or enable billing manually:
```bash
gcloud billing projects link YOUR_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT
```

### Bucket Name Already Taken

```
ERROR: The requested bucket name is not available
```

**Solution**: GCS bucket names are globally unique. The script uses `PROJECT_ID-bucket-name` format to avoid conflicts. If you still get this error, the project ID itself might be too common.

### API Not Enabled

```
ERROR: API [...] is not enabled
```

**Solution**: The script enables APIs automatically, but it may take a few minutes. Wait and try again, or enable manually:
```bash
gcloud services enable APINAME.googleapis.com --project=YOUR_PROJECT_ID
```

### Permission Denied

```
ERROR: Permission denied
```

**Solution**: Make sure you have Owner or Editor role on the project:
```bash
gcloud projects get-iam-policy YOUR_PROJECT_ID
```

## Clean Up (Delete Project)

To completely remove a project created by this script:

```bash
# WARNING: This deletes EVERYTHING (databases, buckets, etc.)
gcloud projects delete YOUR_PROJECT_ID
```

## Manual Setup Alternative

If you prefer to set up manually, see: [COOLIFY_QUICK_START.md](../COOLIFY_QUICK_START.md)

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review [COOLIFY_QUICK_START.md](../COOLIFY_QUICK_START.md)
- Open an issue on GitHub
