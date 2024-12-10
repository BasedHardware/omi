import os
import stripe

stripe.api_key = os.getenv('STRIPE_API_KEY')

def create_product(name, description):
    """Create a new product in Stripe."""
    product = stripe.Product.create(
        name=name,
        description=description,
    )
    return product

def create_app_price(product_id, amount, currency='usd'):
    """Create a price for the given product."""
    price = stripe.Price.create(
        unit_amount=amount,
        currency=currency,
        product=product_id,
    )
    return price

def create_app_payment_link(price_id, app_id):
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
