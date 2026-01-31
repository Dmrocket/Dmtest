import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class InstagramAPIClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.api_version = settings.INSTAGRAM_GRAPH_API_VERSION
        # Ensure we don't double slash if version has a leading slash
        version = self.api_version.lstrip('/')
        self.base_url = f"https://graph.facebook.com/{version}"

    def send_message(self, recipient_id: str, message_text: str, media_url: str = None, comment_id: str = None):
        """
        Sends a message to a user.
        
        Args:
            recipient_id: The Instagram Scoped User ID (IGSID).
            message_text: The text content of the message.
            media_url: Optional URL of an image to send.
            comment_id: Optional ID of the comment to reply to (Private Reply).
            
        Returns:
            dict: The JSON response from the Instagram API.
        """
        url = f"{self.base_url}/me/messages"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Base payload structure
        payload = {
            "messaging_type": "RESPONSE",
            "message": {
                "text": message_text
            }
        }

        # --- CRITICAL AUTOMATION LOGIC ---
        # If comment_id is present, we use it for a "Private Reply".
        # This allows the bot to message the user even if they haven't messaged first,
        # bypassing the standard 24-hour interaction window.
        if comment_id:
            payload["recipient"] = {"comment_id": comment_id}
        else:
            # Standard DM (Only works if user messaged bot in last 24h)
            payload["recipient"] = {"id": recipient_id}

        # Handle Image Attachments
        if media_url:
            payload["message"]["attachment"] = {
                "type": "image", 
                "payload": {
                    "url": media_url, 
                    "is_reusable": True
                }
            }

        try:
            with httpx.Client() as client:
                # 10 second timeout to prevent worker hanging
                response = client.post(url, json=payload, headers=headers, timeout=10.0)
                
                # Raise exception for 4xx/5xx errors
                response.raise_for_status()
                
                return response.json()
                
        except httpx.HTTPStatusError as e:
            # Parse the specific error message from Meta
            try:
                error_data = e.response.json()
                error_msg = error_data.get('error', {}).get('message', str(e))
                logger.error(f"Instagram API Error: {error_msg}")
                raise Exception(f"Instagram API Error: {error_msg}")
            except Exception:
                # If JSON parsing fails, just raise original error
                logger.error(f"HTTP Error sending DM: {str(e)}")
                raise e
                
        except Exception as e:
            logger.error(f"Network/Unexpected Error sending DM: {str(e)}")
            raise e

    def subscribe_to_webhooks(self):
        """
        Enables the 'comments' and 'mentions' fields for the user's page.
        Note: This usually requires the 'instagram_manage_comments' permission.
        """
        # In many cases, subscriptions are handled at the App level via the Dev Portal,
        # but this method can be used to programmatically enable specific fields for a Page.
        # For now, we return True as a placeholder if you are managing subscriptions in the UI.
        return True

    def process_comment(self, payload: dict):
        """
        Helper to extract comment data if needed outside of webhook handler.
        """
        return {
            "id": payload.get("id"),
            "text": payload.get("text"),
            "from_id": payload.get("from", {}).get("id")
        }