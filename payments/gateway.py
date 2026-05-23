"""Payment gateway integration helpers.

This module is intentionally lightweight for future Razorpay integration.
It should remain separate from invoice/payment business logic so gateway-specific
behavior can be added cleanly without polluting existing billing models or templates.
"""

from dataclasses import dataclass


@dataclass
class RazorpayGatewayConfig:
    api_key: str
    api_secret: str
    test_mode: bool = True


class RazorpayGateway:
    def __init__(self, config: RazorpayGatewayConfig):
        self.config = config

    def create_order(self, amount_paise: int, currency: str = 'INR', receipt: str = None, notes: dict = None):
        """Create a Razorpay payment order.

        This is a placeholder for future integration. The current application
        should continue using existing invoice/payment models and forms.
        """
        raise NotImplementedError('Razorpay integration is not enabled yet.')

    def verify_payment_signature(self, payload: dict):
        """Verify a Razorpay payment signature."""
        raise NotImplementedError('Razorpay integration is not enabled yet.')
