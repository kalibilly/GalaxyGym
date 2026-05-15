"""
WhatsApp notification service for Galaxy Gym.

This module handles sending WhatsApp messages for account approvals and rejections.
Supports both mock (development) and real WhatsApp API integration.

Environment variables needed:
- WHATSAPP_API_ENABLED: True/False to enable real WhatsApp API
- WHATSAPP_API_TOKEN: API token for WhatsApp Business API
- WHATSAPP_BUSINESS_ACCOUNT_ID: Business account ID
- WHATSAPP_PHONE_NUMBER_ID: Registered phone number ID for messaging
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_whatsapp_config():
    """Get WhatsApp configuration from environment."""
    return {
        'enabled': os.getenv('WHATSAPP_API_ENABLED', 'False').lower() == 'true',
        'api_token': os.getenv('WHATSAPP_API_TOKEN', ''),
        'business_account_id': os.getenv('WHATSAPP_BUSINESS_ACCOUNT_ID', ''),
        'phone_number_id': os.getenv('WHATSAPP_PHONE_NUMBER_ID', ''),
        'api_version': os.getenv('WHATSAPP_API_VERSION', 'v18.0'),
    }


def send_message_to_whatsapp(phone_number: str, message: str) -> bool:
    """
    Send a message via WhatsApp.
    
    Args:
        phone_number: Recipient's phone number (with country code, e.g., '919876543210')
        message: Message text to send
        
    Returns:
        bool: True if message sent successfully, False otherwise
    """
    config = get_whatsapp_config()
    
    if not config['enabled']:
        logger.info(f'[MOCK] WhatsApp message to {phone_number}: {message}')
        return True
    
    try:
        import requests
        
        url = f"https://graph.instagram.com/{config['api_version']}/{config['phone_number_id']}/messages"
        
        headers = {
            'Authorization': f"Bearer {config['api_token']}",
            'Content-Type': 'application/json',
        }
        
        payload = {
            'messaging_product': 'whatsapp',
            'to': phone_number,
            'type': 'text',
            'text': {'body': message},
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f'WhatsApp message sent to {phone_number}')
            return True
        else:
            logger.error(f'WhatsApp API error ({response.status_code}): {response.text}')
            return False
            
    except Exception as e:
        logger.error(f'Failed to send WhatsApp message to {phone_number}: {str(e)}')
        return False


def send_approval_notification(phone_number: str, name: str, login_id: str) -> bool:
    """
    Send account approval notification via WhatsApp.
    
    Args:
        phone_number: User's phone number
        name: User's full name
        login_id: User's login ID
        
    Returns:
        bool: True if sent successfully
    """
    message = (
        f"Hello {name},\n\n"
        f"Your Galaxy Gym account has been verified successfully. ✅\n\n"
        f"You can now log in using your login ID: {login_id}\n\n"
        f"After login, you may change your password from your profile settings.\n\n"
        f"Welcome to Galaxy Gym! 💪"
    )
    
    return send_message_to_whatsapp(phone_number, message)


def send_rejection_notification(phone_number: str, name: str, reason: str = None) -> bool:
    """
    Send account rejection notification via WhatsApp.
    
    Args:
        phone_number: User's phone number
        name: User's full name
        reason: Rejection reason (optional)
        
    Returns:
        bool: True if sent successfully
    """
    if reason:
        message = (
            f"Hello {name},\n\n"
            f"Your Galaxy Gym signup request could not be verified. ❌\n\n"
            f"Reason: {reason}\n\n"
            f"Please register at the gym first, then request account creation again.\n\n"
            f"Thank you!"
        )
    else:
        message = (
            f"Hello {name},\n\n"
            f"We could not verify your signup request with our gym records. ❌\n\n"
            f"Please register at the gym first, then request account creation again.\n\n"
            f"Thank you!"
        )
    
    return send_message_to_whatsapp(phone_number, message)
