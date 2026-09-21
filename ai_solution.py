To fix the issue, we'll standardize the error messages across all relevant functions. Each function will catch exceptions and return a consistent error message.

```python
# plugins/omi-shopify-app

def shopify_api_request(func, *args, **kwargs):
    try:
        return {"result": func(*args, **kwargs)}
    except Exception as e:
        return {"error": "Request failed."}

def get_analytics():
    try:
        return {"result": shopify_api_request(get_analytics_helper)}
    except Exception as e:
        return {"error": "Failed to get analytics."}

def get_orders():
    try:
        return {"result": shopify_api_request(get_orders_helper)}
    except Exception as e:
        return {"error": "Failed to get orders."}

def get_order_details(order_id):
    try:
        return {"result": shopify_api_request(lambda: get_order_details_helper(order_id))}
    except Exception as e:
        return {"error": "Failed to get order details."}

def create_order(data):
    try:
        return {"result": shopify_api_request(lambda: create_order_helper(data))}
    except Exception as e:
        return {"error": "Failed to create order."}

def get_customers():
    try:
        return {"result": shopify_api_request(get_customers_helper)}
    except Exception as e:
        return {"error": "Failed to get customers."}

def create_customer(data):
    try:
        return {"result": shopify_api_request(lambda: create_customer_helper(data))}
    except Exception as e:
        return {"error": "Failed to create customer."}
```

The code above ensures that each function returns a consistent error message without exposing internal details, enhancing the user experience.