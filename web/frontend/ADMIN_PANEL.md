# Admin Panel Documentation

## Overview

The Admin Panel is a state-of-the-art web interface built with Next.js and shadcn/ui components for reviewing and managing app submissions in the Omi platform.

## Features

### 🔐 Authentication
- Secure admin key-based authentication
- Session persistence using sessionStorage
- Automatic logout capability

### 📊 Dashboard
- **Real-time Statistics**:
  - Total apps pending review
  - Apps needing attention (under-review status)
  - Current search results count

### 🔍 App Review Interface
- **Comprehensive App Listing**:
  - App name, icon, and description
  - Author information
  - Category badges
  - Capabilities display
  - Submission timestamp
  - Current status badges

- **Search & Filtering**:
  - Real-time search across app name, description, and author
  - Quick refresh capability

- **Detailed App View**:
  - Full app metadata
  - External integration details
  - Rating and install statistics
  - Capability tags
  - Timestamp information (created/updated)

### ⚡ Actions
- **Approve App**: Approves the app and notifies the developer
- **Reject App**: Rejects the app and notifies the developer
- **Mark as Popular**: Toggle popular status for featured apps
- **Refresh**: Reload the list of pending apps

### 🎨 UI/UX Features
- Modern, responsive design using shadcn/ui components
- Loading states with spinners
- Toast notifications for all actions
- Color-coded status badges:
  - Green (Default): Approved
  - Red (Destructive): Rejected
  - Gray (Secondary): Under Review
- Gradient background with cards
- Icon-based visual feedback
- Modal dialog for detailed app inspection

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **UI Components**: shadcn/ui (Radix UI primitives)
- **Icons**: Lucide React
- **Styling**: Tailwind CSS
- **State Management**: React Hooks (useState, useEffect)
- **Toast Notifications**: shadcn/ui Toast component

## Installation

The admin panel uses the following shadcn/ui components:

```bash
npx shadcn@latest add table badge tabs select toast dropdown-menu dialog label button input card
```

## Usage

### Accessing the Admin Panel

1. Navigate to `/admin` on your web frontend
2. Enter the admin key (stored in `ADMIN_KEY` environment variable)
3. Click "Login" to authenticate

### Environment Variables

Make sure the following environment variables are set:

```env
ADMIN_KEY=your-secret-admin-key
API_URL=your-backend-api-url
```

### Reviewing Apps

1. **Browse Apps**: View all pending apps in the table
2. **Search**: Use the search bar to filter by name, description, or author
3. **View Details**: Click the eye icon to open detailed view
4. **Take Action**:
   - Click the green checkmark to approve
   - Click the red X to reject
   - Use the star button in detail view to mark as popular

### API Endpoints Used

The admin panel interacts with the following backend endpoints:

- `GET /v1/unapproved-public-apps` - Get all unapproved apps
- `POST /v1/apps/{app_id}/approve?uid={uid}` - Approve an app
- `POST /v1/apps/{app_id}/reject?uid={uid}` - Reject an app
- `PATCH /v1/apps/{app_id}/popular?value={boolean}` - Toggle popular status

All endpoints require the `secret-key` header with the admin key.

## File Structure

```
web/frontend/src/
├── app/
│   └── admin/
│       └── page.tsx           # Main admin panel page
├── lib/
│   └── api/
│       └── admin.ts           # Admin API client functions
└── components/
    └── ui/                    # shadcn/ui components
        ├── table.tsx
        ├── badge.tsx
        ├── dialog.tsx
        ├── toast.tsx
        └── ...
```

## Security Considerations

1. **Admin Key Protection**:
   - The admin key is stored in sessionStorage (not localStorage)
   - Key is cleared on logout
   - All API requests include the key in headers

2. **Access Control**:
   - Backend validates the admin key on every request
   - 403 Forbidden response for invalid keys
   - No server-side rendering of sensitive data

3. **Best Practices**:
   - Use strong, randomly generated admin keys
   - Rotate keys periodically
   - Monitor admin panel access logs
   - Use HTTPS in production

## Component Breakdown

### Main Components

1. **Login Screen**: Simple authentication form with admin key input
2. **Dashboard Header**: Statistics cards with icon indicators
3. **Search Bar**: Real-time filtering with refresh button
4. **Apps Table**: Sortable table with all app information
5. **Detail Modal**: Full-screen dialog with comprehensive app details
6. **Action Buttons**: Approve, reject, and popular toggle buttons

### UI Components from shadcn/ui

- `Card`: Container component for sections
- `Table`: Data table for app listing
- `Badge`: Status and capability indicators
- `Dialog`: Modal for app details
- `Button`: Action buttons with variants
- `Input`: Search and form inputs
- `Label`: Form field labels
- `Toast`: Notification system
- `Tabs`: Future tabbed navigation (ready for expansion)

## Future Enhancements

Potential improvements for the admin panel:

- [ ] Bulk approval/rejection
- [ ] Advanced filtering (by category, capabilities, date range)
- [ ] Sorting columns
- [ ] Pagination for large datasets
- [ ] Activity log/audit trail
- [ ] User management
- [ ] Analytics dashboard
- [ ] App version history
- [ ] Rejection reason notes
- [ ] Email notifications
- [ ] Export functionality (CSV/JSON)
- [ ] Dark mode support

## Troubleshooting

### Common Issues

1. **"Authentication Failed"**
   - Verify the ADMIN_KEY environment variable is set correctly
   - Check that the key matches between frontend and backend

2. **"Failed to fetch apps"**
   - Ensure the backend API is running
   - Verify API_URL is configured correctly
   - Check network connectivity

3. **Empty app list**
   - No apps are currently pending review
   - Check backend logs for errors
   - Verify database connection

## Development

To run the admin panel in development:

```bash
cd web/frontend
npm run dev
```

Then navigate to `http://localhost:3000/admin`

## Building for Production

```bash
cd web/frontend
npm run build
npm start
```

The admin panel will be available at `/admin` on your production domain.
