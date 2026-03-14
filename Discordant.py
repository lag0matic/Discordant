from typing_extensions import override
import asyncio
import threading
import os
import sys
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

# Set up deps path before importing discord
current_dir = os.path.dirname(os.path.abspath(__file__))
deps_path = os.path.join(current_dir, 'deps')
if deps_path not in sys.path:
    sys.path.insert(0, deps_path)

import discord

from lib.PluginHelper import PluginHelper
from lib.PluginSettingDefinitions import PluginSettings, SettingsGrid, TextSetting
from lib.Logger import log
from lib.PluginBase import PluginBase, PluginManifest
from lib.Event import PluginEvent

# ============================================================================
# PARAM MODELS
# ============================================================================

class EmptyParams(BaseModel):
    pass

class ReplyParams(BaseModel):
    message: str                        # Exact dictated reply text

class ReadDMParams(BaseModel):
    sender_name: str                    # Name or partial name of the sender
    limit: Optional[int] = 5           # Number of recent messages to fetch

class CheckDMsParams(BaseModel):
    limit: Optional[int] = 5           # Number of recent conversations to summarise

# ============================================================================
# DISCORD BOT CLIENT
# Runs in a background thread with its own asyncio event loop.
# Connects to Discord Gateway for real-time DM delivery.
#
# NOTE: Messages arrive in the bot's DMs, not your personal account.
# Direct your friends to message the bot instead of your personal Discord.
# You can name the bot anything you like in the Discord Developer Portal.
# ============================================================================

class DiscordantClient(discord.Client):
    def __init__(self, plugin_instance, *args, **kwargs):
        intents = discord.Intents.all()
        super().__init__(intents=intents, *args, **kwargs)
        self.plugin = plugin_instance

    async def on_ready(self):
        log('info', f'DISCORDANT: Bot connected as {self.user} (ID: {self.user.id})')
        self.plugin.bot_user = self.user
        self.plugin.connected = True

    async def on_message(self, message: discord.Message):
        # Only handle DMs, ignore our own messages
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author == self.user:
            return

        sender = message.author.display_name
        content = message.content
        channel_id = message.channel.id

        log('info', f'DISCORDANT: DM received from {sender}: {content[:50]}')

        # Update last DM cache — status generator reads this, no API call needed
        self.plugin.last_dm = {
            'sender': sender,
            'sender_id': message.author.id,
            'channel_id': channel_id,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }

        # Rolling DM history buffer
        self.plugin.dm_history.append(self.plugin.last_dm.copy())
        if len(self.plugin.dm_history) > 50:
            self.plugin.dm_history.pop(0)

        # Fire COVAS event — short prompt only to keep token cost low
        preview = content[:60] + '...' if len(content) > 60 else content
        if self.plugin.helper:
            self.plugin.helper.dispatch_event(PluginEvent(
                plugin_event_name='discord_dm_received',
                plugin_event_content={
                    'sender': sender,
                    'preview': preview,
                    'full_message': content,
                    'channel_id': channel_id
                }
            ))


# ============================================================================
# MAIN PLUGIN CLASS
# ============================================================================

class DiscordantPlugin(PluginBase):

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)

        self.discord_client = None
        self.discord_thread = None
        self.discord_loop = None
        self.bot_user = None
        self.connected = False
        self.helper = None

        # Local state cache — status generator reads these, no API calls per turn
        self.last_dm = None         # Most recent DM received
        self.last_reply = None      # Most recent reply sent
        self.dm_history = []        # Rolling buffer of last 50 DMs received

    settings_config = PluginSettings(
        key="DiscordantPlugin",
        label="Discordant - Discord DM Integration",
        icon="chat",
        grids=[
            SettingsGrid(
                key="discord_credentials",
                label="Discord Bot Credentials",
                fields=[
                    TextSetting(
                        key="bot_token",
                        label="Bot Token",
                        type="text",
                        readonly=False,
                        placeholder="Paste your Discord bot token here",
                        default_value=""
                    ),
                ]
            )
        ]
    )

    @override
    def get_settings_config(self):
        return self.settings_config

    def on_settings_changed(self, settings: dict):
        self.settings = settings

    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------

    @override
    def on_chat_start(self, helper: PluginHelper):
        self.helper = helper
        log('info', 'DISCORDANT: Chat started')

        try:
            # Register the incoming DM event
            helper.register_event(
                name='discord_dm_received',
                should_reply_check=self._should_reply_to_dm,
                prompt_generator=self._dm_prompt
            )

            # Register tools
            helper.register_action(
                'discord_reply',
                "Send a reply to the most recent Discord DM. Pass the exact dictated message.",
                ReplyParams, self.discord_reply, 'global'
            )
            helper.register_action(
                'discord_check_dms',
                "Check recent Discord DMs received this session.",
                CheckDMsParams, self.discord_check_dms, 'global'
            )
            helper.register_action(
                'discord_read_dm',
                "Read the message history in a DM conversation with a specific person.",
                ReadDMParams, self.discord_read_dm, 'global'
            )

            # Status generator — reads local cache only, no API calls per turn
            helper.register_status_generator(self.generate_discord_status)

            # Start Discord bot in background thread
            token = self.settings.get('bot_token', '').strip()
            if token:
                self._start_discord_client(token)
            else:
                log('warning', 'DISCORDANT: No bot token configured. Add token in plugin settings.')

            log('info', 'DISCORDANT: Setup complete')

        except Exception as e:
            log('error', f'DISCORDANT: Failed during chat start: {str(e)}')

    @override
    def on_chat_stop(self, helper: PluginHelper):
        log('info', 'DISCORDANT: Chat stopped — disconnecting bot')
        self._stop_discord_client()
        self.helper = None

    # -------------------------------------------------------------------------
    # BOT THREAD MANAGEMENT
    # -------------------------------------------------------------------------

    def _start_discord_client(self, token: str):
        """Start discord.py bot in a dedicated background thread with its own event loop."""
        try:
            self.discord_loop = asyncio.new_event_loop()
            self.discord_client = DiscordantClient(plugin_instance=self)

            def run_client():
                asyncio.set_event_loop(self.discord_loop)
                try:
                    self.discord_loop.run_until_complete(self.discord_client.start(token))
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log('error', f'DISCORDANT: Bot client error: {str(e)}')
                finally:
                    self.connected = False
                    log('info', 'DISCORDANT: Bot client stopped')

            self.discord_thread = threading.Thread(target=run_client, daemon=True)
            self.discord_thread.start()
            log('info', 'DISCORDANT: Bot thread started')

        except Exception as e:
            log('error', f'DISCORDANT: Failed to start bot: {str(e)}')

    def _stop_discord_client(self):
        """Gracefully shut down the bot and its event loop."""
        try:
            if self.discord_client and self.discord_loop and not self.discord_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    self.discord_client.close(),
                    self.discord_loop
                )
                future.result(timeout=5)
        except Exception as e:
            log('warning', f'DISCORDANT: Error stopping bot: {str(e)}')
        finally:
            self.connected = False
            self.discord_client = None

    def _run_async(self, coro):
        """Run a coroutine on the bot's event loop from a sync context."""
        if not self.discord_loop or self.discord_loop.is_closed():
            raise RuntimeError("Discord event loop is not running.")
        future = asyncio.run_coroutine_threadsafe(coro, self.discord_loop)
        return future.result(timeout=10)

    # -------------------------------------------------------------------------
    # EVENT HANDLERS
    # -------------------------------------------------------------------------

    def _should_reply_to_dm(self, event: PluginEvent) -> bool:
        """Always announce incoming DMs."""
        return True

    def _dm_prompt(self, event: PluginEvent) -> str:
        """
        Short prompt injected into COVAS context when a DM arrives.
        Sender + preview only — keeps token cost low.
        Full content available via discord_read_dm if the user asks.
        """
        sender = event.plugin_event_content.get('sender', 'Unknown')
        full_message = event.plugin_event_content.get('full_message', '')

        if len(full_message) <= 80:
            # Short enough to just read out directly
            return (
                f"Incoming Discord DM from {sender}: \"{full_message}\". "
                f"Inform the user who it's from and read the message."
            )
        else:
            # Longer message — summarise and offer to read in full
            preview = event.plugin_event_content.get('preview', '')
            return (
                f"Incoming Discord DM from {sender}: \"{preview}\". "
                f"Give the user a brief summary. Do not read the full message unless asked."
            )

    # -------------------------------------------------------------------------
    # STATUS GENERATOR
    # Reads from local cache only — no API calls, no token accumulation.
    # -------------------------------------------------------------------------

    def generate_discord_status(self, projected_states: dict) -> list[tuple[str, str]]:
        """Push Discord connection state into context each turn from local cache."""
        try:
            if not self.connected:
                return [("Discord", "Not connected")]

            if not self.last_dm:
                return [("Discord", "Connected — no DMs yet")]

            sender = self.last_dm.get('sender', 'Unknown')
            time_str = self._relative_time(self.last_dm.get('timestamp', ''))

            return [("Discord", f"Connected — last DM: {sender}{time_str}")]

        except Exception as e:
            log('error', f'DISCORDANT: Status generator error: {str(e)}')
            return [("Discord", "Connected")]

    def _relative_time(self, timestamp: str) -> str:
        """Convert ISO timestamp to a relative time string."""
        if not timestamp:
            return ''
        try:
            dt = datetime.fromisoformat(timestamp)
            mins = int((datetime.now() - dt).total_seconds() // 60)
            if mins < 1:
                return ' (just now)'
            elif mins < 60:
                return f' ({mins}m ago)'
            else:
                return f' ({mins // 60}h ago)'
        except:
            return ''

    # -------------------------------------------------------------------------
    # TOOLS
    # -------------------------------------------------------------------------

    def discord_reply(self, args, projected_states) -> str:
        """Send the user's dictated reply to the most recent DM conversation."""
        try:
            if not self.connected or not self.discord_client:
                return "DISCORDANT: Not connected to Discord."

            if not self.last_dm:
                return "DISCORDANT: No recent DM to reply to."

            if not args.message:
                return "DISCORDANT: No message provided."

            channel_id = self.last_dm['channel_id']
            sender = self.last_dm['sender']

            async def send_message():
                channel = await self.discord_client.fetch_channel(channel_id)
                await channel.send(args.message)

            self._run_async(send_message())

            self.last_reply = {
                'recipient': sender,
                'message': args.message,
                'timestamp': datetime.now().isoformat()
            }

            log('info', f'DISCORDANT: Replied to {sender}: {args.message[:50]}')
            return f"DISCORDANT: Reply sent to {sender}."

        except Exception as e:
            log('error', f'DISCORDANT: Reply failed: {str(e)}')
            return f"DISCORDANT: Failed to send reply — {str(e)}"

    def discord_check_dms(self, args, projected_states) -> str:
        """Summarise recent DM conversations from local session history."""
        try:
            if not self.connected:
                return "DISCORDANT: Not connected to Discord."

            if not self.dm_history:
                return "DISCORDANT: No DMs received this session."

            limit = min(args.limit or 5, 20)

            # Most recent message per unique sender
            seen = {}
            for dm in reversed(self.dm_history):
                sender = dm['sender']
                if sender not in seen:
                    seen[sender] = dm
                if len(seen) >= limit:
                    break

            lines = []
            for sender, dm in seen.items():
                preview = dm['content'][:60] + '...' if len(dm['content']) > 60 else dm['content']
                time_str = self._relative_time(dm.get('timestamp', ''))
                lines.append(f"- {sender}{time_str}: \"{preview}\"")

            return "DISCORDANT: Recent DMs:\n" + "\n".join(lines)

        except Exception as e:
            log('error', f'DISCORDANT: Check DMs failed: {str(e)}')
            return f"DISCORDANT: Failed to check DMs — {str(e)}"

    def discord_read_dm(self, args, projected_states) -> str:
        """Fetch recent messages from a DM conversation with a specific person."""
        try:
            if not self.connected or not self.discord_client:
                return "DISCORDANT: Not connected to Discord."

            sender_name = (args.sender_name or '').lower().strip()
            if not sender_name:
                return "DISCORDANT: No sender name provided."

            limit = min(args.limit or 5, 20)

            # Find matching sender in session history
            matches = [
                dm for dm in self.dm_history
                if sender_name in dm['sender'].lower()
            ]

            if not matches:
                return f"DISCORDANT: No DMs from '{args.sender_name}' this session."

            channel_id = matches[-1]['channel_id']
            actual_sender = matches[-1]['sender']

            async def fetch_history():
                channel = await self.discord_client.fetch_channel(channel_id)
                messages = []
                async for msg in channel.history(limit=limit):
                    messages.append(f"{msg.author.display_name}: {msg.content}")
                return list(reversed(messages))

            message_list = self._run_async(fetch_history())

            if not message_list:
                return f"DISCORDANT: No messages found with {actual_sender}."

            return (
                f"DISCORDANT: DM with {actual_sender} (last {len(message_list)} messages):\n"
                + "\n".join(message_list)
            )

        except Exception as e:
            log('error', f'DISCORDANT: Read DM failed: {str(e)}')
            return f"DISCORDANT: Failed to read DM — {str(e)}"
