import os
import requests
from typing import Optional, List, Dict
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()


class SlackClient:
    """Handles Slack API interactions."""
    
    def __init__(self):
        self.client_id = os.getenv("SLACK_CLIENT_ID")
        self.client_secret = os.getenv("SLACK_CLIENT_SECRET")
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """
        Generate Slack OAuth authorization URL.
        Uses USER token scopes so messages appear as sent by the user, not a bot.
        """
        # User token scopes (messages appear as the user)
        # search:read is required for searching messages
        # channels:history is required for reading channel message history
        user_scopes = "channels:read,channels:history,chat:write,groups:read,users:read,search:read"
        
        auth_url = (
            f"https://slack.com/oauth/v2/authorize?"
            f"client_id={self.client_id}&"
            f"user_scope={user_scopes}&"
            f"redirect_uri={redirect_uri}&"
            f"state={state}"
        )
        return auth_url
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns USER token so messages appear as sent by the user, not a bot.
        """
        try:
            response = requests.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    print(f"🔍 OAuth Response Keys: {list(data.keys())}", flush=True)
                    
                    # Use the USER token (authed_user) instead of bot token
                    authed_user = data.get("authed_user", {})
                    user_token = authed_user.get("access_token")
                    
                    if not user_token:
                        # Fallback to bot token if user token not available
                        user_token = data.get("access_token")
                        print("⚠️  WARNING: Using BOT token (user token not available)", flush=True)
                        print(f"⚠️  This means messages will post as BOT, not as USER", flush=True)
                        print(f"⚠️  Check Slack app settings - ensure User Token Scopes are set", flush=True)
                    else:
                        print("✅ Using USER token (messages will appear as user)", flush=True)
                        print(f"✅ User token starts with: {user_token[:15]}...", flush=True)
                    
                    return {
                        "access_token": user_token,
                        "team_id": data.get("team", {}).get("id"),
                        "team_name": data.get("team", {}).get("name"),
                        "scope": data.get("scope"),
                        "token_type": "user" if user_token == authed_user.get("access_token") else "bot"
                    }
                else:
                    raise Exception(f"Slack OAuth error: {data.get('error')}")
            else:
                raise Exception(f"Token exchange failed: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Token exchange error: {e}", flush=True)
            raise
    
    def list_channels(self, access_token: str) -> List[Dict]:
        """
        List all channels the user has access to (public channels, private groups).
        Returns list of {id, name, is_channel, is_group, is_im, is_private}
        Handles pagination to get all channels.
        """
        client = WebClient(token=access_token)
        channels = []
        
        try:
            cursor = None
            page_count = 0
            
            while True:
                # Get channels with pagination
                params = {
                    "types": "public_channel,private_channel",
                    "exclude_archived": True,
                    "limit": 200
                }
                if cursor:
                    params["cursor"] = cursor
                
                result = client.conversations_list(**params)
                
                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    print(f"❌ Error listing channels: {error}", flush=True)
                    break
                
                page_channels = result.get("channels", [])
                page_count += 1
                
                for channel in page_channels:
                    channel_info = {
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_channel": channel.get("is_channel", False),
                        "is_group": channel.get("is_group", False),
                        "is_private": channel.get("is_private", False),
                        "is_member": channel.get("is_member", False)
                    }
                    channels.append(channel_info)
                    # Log each channel for debugging
                    member_status = "member" if channel_info["is_member"] else "not a member"
                    privacy = "private" if channel_info["is_private"] else "public"
                    print(f"  📢 channel: #{channel_info['name']} ({privacy}, {member_status})", flush=True)
                
                # Check if there are more pages
                response_metadata = result.get("response_metadata", {})
                cursor = response_metadata.get("next_cursor")
                
                if not cursor:
                    break
            
            # Log summary
            public_channels = [c for c in channels if not c.get("is_private")]
            private_channels = [c for c in channels if c.get("is_private")]
            member_channels = [c for c in channels if c.get("is_member")]
            
            print(f"✅ Listed {len(channels)} total channels across {page_count} page(s)", flush=True)
            print(f"   📊 Breakdown: {len(public_channels)} public, {len(private_channels)} private", flush=True)
            print(f"   👤 User is member of: {len(member_channels)} channels", flush=True)
            
            # Important note about Slack API behavior
            if len(channels) == 1:
                print(f"⚠️  Only 1 channel found - Slack API only returns channels user is a member of", flush=True)
                print(f"⚠️  To see more channels, user needs to join them in Slack first", flush=True)
            
            return channels
            
        except SlackApiError as e:
            error_msg = e.response.get('error', str(e))
            print(f"❌ Error listing channels: {error_msg}", flush=True)
            return []
        except Exception as e:
            print(f"❌ Error listing channels: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return []
    
    async def send_message(
        self,
        access_token: str,
        channel_id: str,
        text: str
    ) -> Optional[dict]:
        """
        Send a message to a Slack channel as the authenticated user.
        With user tokens, messages automatically post as the user.
        Returns message data if successful.
        """
        client = WebClient(token=access_token)
        
        # Debug: Check token type
        token_prefix = access_token[:15] if access_token else "None"
        token_type = "USER" if access_token and access_token.startswith("xoxp-") else "BOT" if access_token and access_token.startswith("xoxb-") else "UNKNOWN"
        print(f"🔑 Sending with {token_type} token: {token_prefix}...", flush=True)
        
        try:
            # Note: as_user parameter is deprecated and not needed with user tokens
            # User tokens automatically post messages as the authenticated user
            result = client.chat_postMessage(
                channel=channel_id,
                text=text
            )
            
            if result.get("ok"):
                # Check if message was posted by bot or user
                message_data = result.get("message", {})
                subtype = message_data.get("subtype")
                bot_id = message_data.get("bot_id")
                username = message_data.get("username", "N/A")
                
                if bot_id:
                    print(f"⚠️  Message posted as BOT (bot_id: {bot_id})", flush=True)
                else:
                    print(f"✅ Message posted as USER", flush=True)
                
                return {
                    "success": True,
                    "ts": result.get("ts"),
                    "channel": result.get("channel"),
                    "text": text,
                    "posted_as": "bot" if bot_id else "user"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
                
        except SlackApiError as e:
            error_msg = e.response.get('error', str(e))
            print(f"❌ Slack API error: {error_msg}", flush=True)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            print(f"❌ Error sending message: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_channel_history(
        self,
        access_token: str,
        channel_id: str,
        limit: int = 100,
        oldest: Optional[float] = None
    ) -> Optional[dict]:
        """
        Get message history from a specific channel.
        Use this for getting recent messages (like today's messages).
        Requires channels:history scope.
        """
        client = WebClient(token=access_token)
        
        try:
            params = {
                "channel": channel_id,
                "limit": limit
            }
            if oldest:
                params["oldest"] = oldest
            
            result = client.conversations_history(**params)
            
            if result.get("ok"):
                messages = result.get("messages", [])
                return {
                    "success": True,
                    "messages": messages,
                    "total": len(messages)
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
                
        except SlackApiError as e:
            error_msg = e.response.get('error', str(e))
            print(f"❌ Slack API error getting channel history: {error_msg}", flush=True)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            print(f"❌ Error getting channel history: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def search_messages(
        self,
        access_token: str,
        query: str,
        channel: Optional[str] = None
    ) -> Optional[dict]:
        """
        Search for messages in Slack.
        For recent messages in a specific channel, prefers using channel history.
        Returns list of matching messages.
        """
        client = WebClient(token=access_token)
        
        try:
            # If searching in a specific channel and query is simple (like "today" or empty),
            # use channel history instead of search API for better results
            if channel:
                # Find channel ID
                channels = self.list_channels(access_token)
                channel_id = None
                channel_name = None
                
                if not channel.startswith('C') and not channel.startswith('G'):
                    # It's a channel name, find the ID
                    channel_search = channel.lower().lstrip('#')
                    for ch in channels:
                        if ch["name"].lower() == channel_search:
                            channel_id = ch["id"]
                            channel_name = ch["name"]
                            break
                else:
                    channel_id = channel
                    # Find channel name
                    for ch in channels:
                        if ch["id"] == channel_id:
                            channel_name = ch["name"]
                            break
                
                if channel_id:
                    # Check if query is asking for recent messages (today, recent, etc.)
                    query_lower = query.lower().strip()
                    is_recent_query = (
                        not query_lower or 
                        query_lower in ["today", "recent", "latest", "last", "new", "*", "all"]
                    )
                    
                    # Also check if query contains date filters (after/before) - use search for those
                    has_date_filter = "after:" in query_lower or "before:" in query_lower
                    
                    if is_recent_query and not has_date_filter:
                        print(f"📅 Using channel history for recent messages in #{channel_name} (query: '{query}')", flush=True)
                        # Get messages from today (last 24 hours) or all recent if query is '*'
                        from datetime import datetime, timedelta
                        
                        # For '*' or 'all', get more messages (last 7 days), otherwise just today
                        if query_lower in ["*", "all"]:
                            days_back = 7
                            limit = 200
                        else:
                            days_back = 1
                            limit = 100
                        
                        cutoff_date = datetime.now() - timedelta(days=days_back)
                        oldest_timestamp = cutoff_date.timestamp()
                        
                        history_result = self.get_channel_history(
                            access_token=access_token,
                            channel_id=channel_id,
                            limit=limit,
                            oldest=oldest_timestamp
                        )
                        
                        if history_result and history_result.get("success"):
                            messages = history_result.get("messages", [])
                            print(f"📊 Got {len(messages)} messages from channel history", flush=True)
                            
                            # Filter out bot messages and system messages
                            user_messages = [
                                msg for msg in messages 
                                if not msg.get("bot_id") and not msg.get("subtype")
                            ]
                            
                            print(f"📊 Filtered to {len(user_messages)} user messages", flush=True)
                            
                            return {
                                "success": True,
                                "matches": user_messages,
                                "total": len(user_messages),
                                "source": "channel_history"
                            }
                        else:
                            error = history_result.get("error", "Unknown error") if history_result else "Failed"
                            print(f"⚠️  Channel history failed ({error}), falling back to search", flush=True)
            
            # Use search API for general searches
            search_query = query
            if channel:
                # If channel is provided, search within that channel
                if not channel.startswith('C') and not channel.startswith('G'):
                    # It's a channel name, need to find the ID
                    channels = self.list_channels(access_token)
                    channel_id = None
                    for ch in channels:
                        if ch["name"].lower() == channel.lower().lstrip('#'):
                            channel_id = ch["id"]
                            break
                    if channel_id:
                        search_query = f"in:{channel_id} {query}"
                else:
                    search_query = f"in:{channel} {query}"
            
            print(f"🔍 Using search API with query: '{search_query}'", flush=True)
            result = client.search_messages(query=search_query)
            
            if result.get("ok"):
                matches = result.get("messages", {}).get("matches", [])
                return {
                    "success": True,
                    "matches": matches,
                    "total": len(matches),
                    "source": "search"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
                
        except SlackApiError as e:
            error_msg = e.response.get('error', str(e))
            print(f"❌ Slack API error searching messages: {error_msg}", flush=True)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            print(f"❌ Error searching messages: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def search_channels(
        self,
        access_token: str,
        query: str
    ) -> List[Dict]:
        """
        Search for channels matching the query string.
        Returns list of matching channels.
        If query is empty or "all", returns all channels.
        """
        client = WebClient(token=access_token)
        matching_channels = []
        
        try:
            # Get all channels
            all_channels = self.list_channels(access_token)
            
            # If query is empty or "all", return all channels
            if not query or query.lower().strip() == "all":
                print(f"🔍 Returning all {len(all_channels)} channels (query: '{query}')", flush=True)
                return all_channels
            
            # Filter channels by query (case-insensitive)
            query_lower = query.lower().lstrip('#').strip()
            for channel in all_channels:
                channel_name = channel.get("name", "").lower()
                if query_lower in channel_name:
                    matching_channels.append(channel)
            
            print(f"🔍 Found {len(matching_channels)} channels matching '{query}'", flush=True)
            return matching_channels
            
        except Exception as e:
            print(f"❌ Error searching channels: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return []

