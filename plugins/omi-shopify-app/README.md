# Shopify Integration for Omi

Manage your Shopify store with voice commands through your Omi device. Get analytics, manage orders, and handle customers – all hands-free!

---

## 🛒 Features

- **📊 Analytics Dashboard** - Get sales, orders, and revenue insights
- **📦 Order Management** - View, search, and create orders with voice
- **👥 Customer Management** - Search customers and add new ones instantly
- **🔐 Secure OAuth** - Industry-standard Shopify OAuth 2.0 authentication

---

## 🚀 Quick Start

1. Install the Shopify app from the Omi App Store
2. Enter your store domain (e.g., `your-store.myshopify.com`)
3. Authorize the app in Shopify
4. Start using voice commands!

---

## 🗣️ Voice Commands

| Command                                           | Description                    |
| ------------------------------------------------- | ------------------------------ |
| "Show my analytics for today"                     | Get today's sales and orders   |
| "What were my sales last 7 days?"                 | Analytics for the past week    |
| "Show analytics from Nov 28 to Dec 2"             | Custom date range (e.g., BFCM) |
| "What were my BFCM sales from Thursday to Monday" | Custom date range analytics    |
| "Show my recent orders"                           | List latest orders             |
| "Get details for order #1001"                     | View specific order info       |
| "Show pending orders"                             | Filter by payment status       |
| "Create an order for john@example.com"            | Create a new order             |
| "Show my customers"                               | List your customers            |
| "Search customer john@example.com"                | Find a specific customer       |
| "Create a customer for jane@example.com"          | Add new customer               |

---

## 📋 Omi App Store Details

### App Information

| Field           | Value                                                                                                                                        |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **App Name**    | Shopify                                                                                                                                      |
| **Category**    | Business & Productivity                                                                                                                      |
| **Description** | Manage your Shopify store with voice commands. Get analytics, view orders, create orders, and manage customers – all hands-free through Omi. |
| **Author**      | Omi Community                                                                                                                                |
| **Version**     | 1.0.0                                                                                                                                        |

### Capabilities

- ✅ **External Integration** (required for chat tools)
- ✅ **Chat** (for voice command responses)

### URLs for Omi App Configuration

| URL Type                    | URL                                                                                 |
| --------------------------- | ----------------------------------------------------------------------------------- |
| **App Home URL**            | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/`                           |
| **Auth URL**                | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/`                           |
| **Setup Completed URL**     | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/setup/shopify`              |
| **Chat Tools Manifest URL** | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/.well-known/omi-tools.json` |

> **Note:** The Auth URL is the same as App Home URL because Shopify requires users to enter their store domain before OAuth. Omi automatically appends `?uid=USER_ID` to these URLs.

---

## 🔧 Shopify App Configuration

### Redirect URI (Add to Shopify Partner Dashboard)

Add this redirect URI to your Shopify app in the [Shopify Partner Dashboard](https://partners.shopify.com/):

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/auth/shopify/callback
```

### App Credentials

| Field             | Value                                    |
| ----------------- | ---------------------------------------- |
| **Client ID**     | `YOUR_CLIENT_ID_HERE`       |
| **Client Secret** | `YOUR_CLIENT_SECRET_HERE` |

### Required Scopes

The app uses the following Shopify API scopes:

- `read_all_orders` - Read all orders
- `read_analytics` - Read store analytics
- `read_customers` - Read customer data
- `write_customers` - Create/update customers
- `write_draft_orders` - Create draft orders
- `read_draft_orders` - Read draft orders
- `read_orders` - Read orders
- `write_orders` - Create/update orders

---

## 🔧 Chat Tools

This app exposes a manifest endpoint at `/.well-known/omi-tools.json` that Omi automatically fetches when the app is created or updated.

### Chat Tools Manifest URL

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/.well-known/omi-tools.json
```

### Available Tools

| Tool                | Description                                       |
| ------------------- | ------------------------------------------------- |
| `get_analytics`     | Get store analytics (sales, orders, revenue)      |
| `get_orders`        | List recent orders with filters                   |
| `get_order_details` | Get detailed info about a specific order          |
| `create_order`      | Create a new order (auto-creates customer if new) |
| `get_customers`     | List/search customers                             |
| `create_customer`   | Create a new customer                             |

---

## 🛠️ Development

### Prerequisites

- Python 3.8+
- Shopify Partner Account
- ngrok (for local development)

### Local Setup

```bash
# Navigate to the plugin directory
cd plugins/shopify

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your ngrok URL

# Run the server
python main.py
```

### Environment Variables

```env
SHOPIFY_CLIENT_ID=YOUR_CLIENT_ID_HERE
SHOPIFY_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE
SHOPIFY_REDIRECT_URI=https://your-ngrok-url.ngrok-free.app/auth/shopify/callback
PORT=8080
REDIS_URL=  # Optional: for production use
```

### Running with ngrok

```bash
# Terminal 1: Run the server
cd plugins/shopify
source venv/bin/activate
python main.py

# Terminal 2: Start ngrok
ngrok http 8080
```

---

## 📡 API Endpoints

| Endpoint                      | Method | Description                  |
| ----------------------------- | ------ | ---------------------------- |
| `/`                           | GET    | Home page / App settings     |
| `/health`                     | GET    | Health check                 |
| `/auth/shopify`               | GET    | Start OAuth flow             |
| `/auth/shopify/callback`      | GET    | OAuth callback               |
| `/setup/shopify`              | GET    | Check setup status           |
| `/disconnect`                 | GET    | Disconnect store             |
| `/.well-known/omi-tools.json` | GET    | Chat tools manifest          |
| `/tools/get_analytics`        | POST   | Chat tool: Get analytics     |
| `/tools/get_orders`           | POST   | Chat tool: Get orders        |
| `/tools/get_order_details`    | POST   | Chat tool: Get order details |
| `/tools/create_order`         | POST   | Chat tool: Create order      |
| `/tools/get_customers`        | POST   | Chat tool: Get customers     |
| `/tools/create_customer`      | POST   | Chat tool: Create customer   |

---

## 🚀 Deploy to Railway

### Step 1: Create Railway Project

1. Go to [Railway](https://railway.app) and sign in
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository and choose the `plugins/shopify` folder

### Step 2: Add Redis Database (Optional)

1. In your Railway project, click **"+ New"** → **"Database"** → **"Add Redis"**
2. Railway automatically creates and connects the Redis instance
3. The `REDIS_URL` environment variable is set automatically

### Step 3: Configure Environment Variables

Go to your service's **Variables** tab and add:

| Variable                | Value                                                   |
| ----------------------- | ------------------------------------------------------- |
| `SHOPIFY_CLIENT_ID`     | `YOUR_CLIENT_ID_HERE`                      |
| `SHOPIFY_CLIENT_SECRET` | `YOUR_CLIENT_SECRET_HERE`                |
| `SHOPIFY_REDIRECT_URI`  | `https://YOUR-APP.up.railway.app/auth/shopify/callback` |

### Step 4: Update Shopify Partner Dashboard

Add your Railway URL as a redirect URI:

```
https://YOUR-APP.up.railway.app/auth/shopify/callback
```

### Step 5: Update Omi App Store

Update your app URLs in the Omi App Store:

| URL Type                    | Value                                                        |
| --------------------------- | ------------------------------------------------------------ |
| **App Home URL**            | `https://YOUR-APP.up.railway.app/`                           |
| **Auth URL**                | `https://YOUR-APP.up.railway.app/`                           |
| **Setup Completed URL**     | `https://YOUR-APP.up.railway.app/setup/shopify`              |
| **Chat Tools Manifest URL** | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |

---

## 🐛 Troubleshooting

### "User not authenticated"

- Complete the Shopify OAuth flow by entering your store domain and authorizing the app

### "Failed to get analytics/orders"

- Verify your Shopify app has the correct API scopes enabled
- Check that your store's API access is not restricted

### "Order creation failed"

- Ensure line items have valid title, quantity, and price
- Verify customer email is valid

### "Invalid callback parameters"

- Make sure the redirect URI in Shopify Partner Dashboard matches exactly

---

## 📄 License

MIT License - feel free to modify and distribute.

---

## 🤝 Support

For issues or feature requests, please open an issue on GitHub or contact the Omi community.

---

Made with ❤️ for Omi
