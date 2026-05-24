"""Payment gateway integration helpers.

This module keeps Razorpay-specific behavior isolated from invoice and
membership business logic. The gateway layer may be extended later once the
Razorpay SDK and credentials are configured.
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
        """Create a Razorpay payment order."""
        try:
            import razorpay
        except ImportError as exc:
            raise RuntimeError('Razorpay SDK is not installed.') from exc

        client = razorpay.Client(auth=(self.config.api_key, self.config.api_secret))
        order_payload = {
            'amount': amount_paise,
            'currency': currency,
            'receipt': receipt,
            'notes': notes or {},
            'payment_capture': 1,
        }
        return client.order.create(order_payload)

    def verify_payment_signature(self, payload: dict):
        """Verify a Razorpay payment signature."""
        try:
            import razorpay
        except ImportError as exc:
            raise RuntimeError('Razorpay SDK is not installed.') from exc

        return razorpay.Utility.verify_payment_signature(payload)
