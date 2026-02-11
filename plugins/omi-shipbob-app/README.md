# ShipBob Integration for Omi

A voice-enabled ShipBob integration for Omi that allows users to manage inventory, create Warehouse Receiving Orders (WROs), and track orders using natural language.

## Features

- **Inventory Management**: Check stock levels and fulfillable quantities
- **Product Search**: Find products by name
- **WRO Creation**: Create Warehouse Receiving Orders to send inventory to ShipBob
- **WRO Management**: View and cancel WROs
- **Order Tracking**: View recent orders and their status
- **Fulfillment Centers**: List available warehouse locations

## Setup

### Prerequisites

1. A ShipBob account with API access
2. ShipBob OAuth2 credentials (Client ID and Client Secret)
3. Redis instance (for production token storage)

### Environment Variables

Create a `.env` file with the following variables:

```env
# ShipBob OAuth2 Credentials
SHIPBOB_CLIENT_ID=your_client_id
SHIPBOB_CLIENT_SECRET=your_client_secret
SHIPBOB_REDIRECT_URI=https://your-domain.com/auth/shipbob/callback

# ShipBob API URLs (Production)
SHIPBOB_AUTH_URL=https://auth.shipbob.com/connect/authorize
SHIPBOB_TOKEN_URL=https://auth.shipbob.com/connect/token
SHIPBOB_API_URL=https://api.shipbob.com

# For Sandbox/Testing, use:
# SHIPBOB_AUTH_URL=https://authstage.shipbob.com/connect/authorize
# SHIPBOB_TOKEN_URL=https://authstage.shipbob.com/connect/token
# SHIPBOB_API_URL=https://sandbox-api.shipbob.com

# Redis (for production)
REDIS_URL=redis://localhost:6379
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

### Deploy to Railway

1. Create a new project on Railway
2. Add a Redis service
3. Set the environment variables
4. Deploy from this directory

## Omi App Configuration

When creating the Omi app, use these URLs (replace `YOUR_DOMAIN` with your deployed URL):

| Setting | URL |
|---------|-----|
| **App Home URL** | `https://YOUR_DOMAIN/?uid={{uid}}` |
| **Setup Completed URL** | `https://YOUR_DOMAIN/setup/shipbob?uid={{uid}}` |
| **Auth URL** | `https://YOUR_DOMAIN/auth/shipbob?uid={{uid}}` |
| **Chat Tools URL** | `https://YOUR_DOMAIN/.well-known/omi-tools.json` |

## Chat Tools Available

1. **get_inventory** - Check inventory levels
2. **get_products** - List and search products
3. **create_wro** - Create Warehouse Receiving Orders
4. **get_wros** - View WROs and their status
5. **cancel_wro** - Cancel a pending WRO
6. **get_orders** - View recent orders
7. **get_fulfillment_centers** - List fulfillment centers

## Example Voice Commands

- "Check inventory for Blue T-Shirt"
- "How much stock do we have?"
- "Create a WRO for 100 units of Widget Pro"
- "Show me my WROs"
- "Cancel WRO 12345"
- "Show me my recent orders"
- "List all fulfillment centers"

## API Reference

- [ShipBob Developer Portal](https://developer.shipbob.com/)
- [ShipBob Authentication](https://developer.shipbob.com/auth)
- [ShipBob API Reference](https://developer.shipbob.com/api-docs)

## License

MIT
