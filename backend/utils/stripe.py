import os
import stripe

stripe.api_key = os.getenv('STRIPE_API_KEY')
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

def create_product(name: str, description: str, image: str):
    """Create a new product in Stripe."""
    product = stripe.Product.create(
        name=name,
        description=description,
        images=[image] if image and len(image) > 0 else [],
        tax_code="txcd_10103000",  # saas
    )
    return product

def create_app_monthly_recurring_price(product_id:str, amount_in_cents: int, currency:str = 'usd'):
    """Create a price for the given product."""
    price = stripe.Price.create(
        unit_amount=amount_in_cents,
        currency=currency,
        product=product_id,
        recurring={'interval': 'month'},
    )
    return price

def create_app_payment_link(price_id:str, app_id: str):
    """Create a payment link for the specified price."""
    payment_link = stripe.PaymentLink.create(
        line_items=[{
            'price': price_id,
            'quantity': 1,
        }],
        metadata={
            'app_id': app_id
        },
    )
    return payment_link


def parse_event(payload, sig_header):
    """Parse the Stripe event."""
    return stripe.Webhook.construct_event(
        payload, sig_header, endpoint_secret
    )
