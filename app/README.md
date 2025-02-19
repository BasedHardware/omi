# Friend App

The Friend App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

### Automated Setup (Recommended)

1. Navigate to the app directory:
   ```bash
   cd app
   ```

2. Run setup script:
   ```bash
   # For iOS
   bash setup.sh ios

   # For Android
   bash setup.sh android
   ```

3. Run the app:
   ```bash
   flutter run --flavor dev
   ```

For detailed setup instructions, including manual setup and Firebase configuration, visit our [App Setup Guide](https://docs.omi.me/docs/developer/AppSetup).

## Key Features

- **Device Management**: Connect and manage Omi devices
- **App Marketplace**: Browse, install, and manage apps
- **Chat Interface**: Interact with your Omi device
- **External Integrations**: Support for various services and APIs
- **Payment Integration**: Secure payment processing through Stripe
- **Developer Tools**: Create and publish your own apps

## Project Structure

- `lib/`: Main application code
  - `pages/`: UI screens and components
  - `providers/`: State management
  - `backend/`: API and backend services
  - `utils/`: Utility functions and helpers

## Support

- Discord: http://discord.omi.me
- Documentation: https://docs.omi.me
