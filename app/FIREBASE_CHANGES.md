# Firebase Configuration Changes

This document summarizes the changes made to implement Firebase configuration using environment variables.

## Overview

We've updated the Firebase configuration system to use environment variables instead of hardcoded values. This approach has several advantages:

1. **Security**: Sensitive information is not hardcoded in the source code
2. **Flexibility**: Easily switch between different Firebase projects
3. **Maintainability**: Centralized configuration management

## Changes Made

### 1. Environment Variables Structure

- Added Firebase configuration variables to `.env.template` and `.dev.env`
- Updated the environment classes (`Env`, `DevEnv`, `ProdEnv`) to include Firebase configuration getters

### 2. Firebase Options from Environment

- Created a new `firebase_options_env.dart` file that loads Firebase options from environment variables
- Updated the Firebase initialization in `main.dart` to try using environment variables first, with a fallback to hardcoded options

### 3. Setup Script Update

- Updated the `setup.sh` script to add Firebase configuration to environment files during setup
- Updated the `initialsetup.bash` script to include Firebase environment variables setup

### 4. Documentation

- Updated `README.md` with information about the new Firebase configuration approach
- Created a detailed `FIREBASE_SETUP.md` guide
- Updated `Tasks.md` to include the Firebase configuration task

### 5. Migration Tool

- Created a script (`scripts/firebase_config_to_env.dart`) to extract Firebase configuration from hardcoded files and generate environment variable entries

## Fallback Mechanism

To ensure backward compatibility, we've implemented a fallback mechanism:

1. The app first tries to use Firebase configuration from environment variables
2. If environment variables are missing or incomplete, it falls back to the hardcoded configuration
3. This ensures that existing setups continue to work while allowing for the new approach

## How to Use

1. Update your `.dev.env` file with your Firebase project details
2. Run `dart run build_runner build` to generate the necessary files
3. The app will automatically use these environment variables for Firebase initialization

For detailed instructions, see the `FIREBASE_SETUP.md` guide.

## Files Modified

- `app/.env.template`
- `app/.dev.env`
- `app/lib/env/env.dart`
- `app/lib/env/dev_env.dart`
- `app/lib/env/prod_env.dart`
- `app/lib/firebase_options_env.dart` (new file)
- `app/lib/main.dart`
- `app/setup.sh`
- `app/initialsetup.bash`
- `app/README.md`
- `app/FIREBASE_SETUP.md` (new file)
- `app/Tasks.md`
- `app/scripts/firebase_config_to_env.dart` (new file)