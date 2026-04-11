"""
J.A.R.V.I.S -- Messaging Plugin
Send messages via WhatsApp, Telegram, Instagram, Discord, and more.

Automates message sending through desktop/web apps using PyAutoGUI.
Example: "text Aryan on WhatsApp hello bro" -> opens WhatsApp, finds contact, sends message.

Commands:
    /msg <app> <contact> <message>     -- Send a message via any app
    /whatsapp <contact> <message>      -- Send via WhatsApp
    /telegram <contact> <message>      -- Send via Telegram
"""

import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from core.plugin_manager import PluginBase

# ---------------------------------------------------------------------------
# Graceful imports for automation dependencies
# ---------------------------------------------------------------------------

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False

logger = logging.getLogger("jarvis.messaging")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTACTS_FILE = Path.home() / ".jarvis_contacts.json"

APP_URI_MAP = {
    "whatsapp": "whatsapp:",
    "telegram": "telegram:",
    "discord": "discord:",
}

APP_WEB_FALLBACKS = {
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "instagram": "https://www.instagram.com/direct/inbox/",
    "discord": "https://discord.com/channels/@me",
}


# ===========================================================================
# MessagingPlugin
# ===========================================================================

class MessagingPlugin(PluginBase):
    """Send messages via WhatsApp, Telegram, Instagram, Discord, and more."""

    name = "messaging"
    description = "Send messages via WhatsApp, Telegram, Instagram, and more"
    version = "1.0"

    # ── Lifecycle ─────────────────────────────────────────────

    def activate(self):
        self.contacts: dict = self._load_contacts()
        self.message_queue: list[dict] = []
        self._queue_lock = threading.Lock()
        logger.info("[messaging] Plugin activated")

    def deactivate(self):
        logger.info("[messaging] Plugin deactivated")

    # ── Command router ────────────────────────────────────────

    def on_command(self, command: str, args: str) -> bool:
        if command == "/msg":
            return self._handle_msg(args)
        if command == "/whatsapp":
            return self._handle_shortcut("whatsapp", args)
        if command == "/telegram":
            return self._handle_shortcut("telegram", args)
        return False

    def _handle_msg(self, args: str) -> bool:
        """Parse: /msg <app> <contact> <message>"""
        parts = args.strip().split(None, 2)
        if len(parts) < 3:
            self._reply("Usage: /msg <app> <contact> <message>")
            return True
        app, contact, message = parts[0].lower(), parts[1], parts[2]
        self._send_in_thread(app, contact, message)
        return True

    def _handle_shortcut(self, app: str, args: str) -> bool:
        """Parse: /<app> <contact> <message>"""
        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            self._reply(f"Usage: /{app} <contact> <message>")
            return True
        contact, message = parts[0], parts[1]
        self._send_in_thread(app, contact, message)
        return True

    # ── Natural-language intercept ────────────────────────────

    def on_message(self, message: str) -> str | None:
        """
        Detect natural language requests like:
          - "text Aryan on WhatsApp hello bro"
          - "send a message to Aryan on telegram saying hi"
        Returns None to pass through if no match.
        """
        lower = message.lower()
        triggers = [
            "text ", "message ", "send a message", "msg ",
            "dm ", "send on whatsapp", "send on telegram",
        ]
        if not any(t in lower for t in triggers):
            return None

        # Let the AI handle the parsing -- we just flag that messaging is relevant
        return None

    # ── Core send logic ───────────────────────────────────────

    def send_message(self, app: str, contact: str, message: str) -> dict:
        """
        Main entry point. Shows a permission dialog, then dispatches to the
        app-specific sender.

        Returns:
            dict with keys: success (bool), message (str)
        """
        if not HAS_PYAUTOGUI:
            return {"success": False, "message": "pyautogui is not installed. Run: pip install pyautogui"}

        # ── Permission dialog (MANDATORY) ─────────────────────
        if not self._ask_permission(app, contact, message):
            return {"success": False, "message": "User declined to send the message."}

        # ── Resolve contact name from contact book ────────────
        resolved = self.get_contact(contact, app) or contact
        if app.lower() == "whatsapp" and not self._is_plausible_whatsapp_title(contact, resolved):
            resolved = contact

        # ── Dispatch ──────────────────────────────────────────
        dispatchers = {
            "whatsapp": self._send_whatsapp,
            "telegram": self._send_telegram,
            "instagram": self._send_instagram,
            "discord": self._send_discord,
        }

        sender = dispatchers.get(app, None)
        if sender:
            if app == "whatsapp":
                result = sender(resolved, message, alias=contact)
            else:
                result = sender(resolved, message)
        else:
            result = self._send_generic(app, resolved, message)

        # ── Learn the contact on success ──────────────────────
        if result.get("success"):
            result_data = result.get("data") or {}
            learned_contact = result_data.get("selected_contact") or resolved
            self.add_contact(contact, app, learned_contact)

        return result

    # ── Permission dialog ─────────────────────────────────────

    def _ask_permission(self, app: str, contact: str, message: str) -> bool:
        """
        Ask permission before sending a message.
        Uses VERBAL confirmation when voice is active (no popups!),
        falls back to tkinter dialog when voice is off.
        """
        # Try verbal confirmation first (feels like JARVIS)
        voice = self.jarvis.plugin_manager.plugins.get("voice")
        if voice and voice.is_enabled:
            if getattr(voice, "uses_gemini_live", lambda: False)():
                return True
            question = (
                f"Shall I send \"{message}\" to {contact} on {app.title()}?"
            )
            return voice.verbal_confirm(question)

        permission_hook = getattr(self.jarvis, "request_permission", None)
        if callable(permission_hook):
            question = (
                f"Shall I send \"{message}\" to {contact} on {app.title()}?"
            )
            try:
                return bool(permission_hook(
                    question,
                    kind="messaging",
                    app=app,
                    contact=contact,
                    message=message,
                ))
            except TypeError:
                return bool(permission_hook(question))

        # Fallback: tkinter dialog (when voice is off / typing mode)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            prompt = (
                f"JARVIS wants to send a message:\n\n"
                f"  App:     {app.title()}\n"
                f"  To:      {contact}\n"
                f"  Message: \"{message}\"\n\n"
                f"Send this message?"
            )

            result = messagebox.askyesno("JARVIS — Confirm Message", prompt, parent=root)
            root.destroy()
            return result
        except Exception as e:
            logger.error(f"Permission dialog failed: {e}")
            return False

    # ── App-specific senders ──────────────────────────────────

    def _normalize_ui_text(self, text: str) -> str:
        return " ".join((text or "").lower().split())

    def _tokenize_ui_text(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", self._normalize_ui_text(text))

    def _ui_text_contains_message(self, text: str, message: str) -> bool:
        normalized_text = self._normalize_ui_text(text)
        normalized_message = self._normalize_ui_text(message)
        if not normalized_text or not normalized_message:
            return False
        if normalized_message in normalized_text:
            return True
        snippet = normalized_message[: max(12, min(len(normalized_message), 28))]
        return snippet in normalized_text

    def _whatsapp_composer_descriptions(self) -> tuple[str, ...]:
        return (
            "the bottom message input box in the active WhatsApp chat labeled Type a message",
            "the chat composer at the bottom of the active WhatsApp conversation",
            "the message field at the bottom center of the current WhatsApp chat",
        )

    def _whatsapp_wrong_panel_descriptions(self) -> tuple[str, ...]:
        return (
            "the Add group members search field in the left WhatsApp panel",
            "the search field in the left WhatsApp sidebar",
            "the left sidebar input field in WhatsApp",
        )

    def _whatsapp_blocked_state_descriptions(self) -> tuple[str, ...]:
        return (
            "the bottom action area in the active WhatsApp chat showing buttons like Unblock or Delete chat",
            "the lower section of the current WhatsApp conversation where Unblock or Delete chat appears instead of a message box",
            "the bottom of the active WhatsApp chat showing chat-management actions instead of the Type a message composer",
        )

    def _whatsapp_sent_message_descriptions(self) -> tuple[str, ...]:
        return (
            "the newest outgoing message bubble at the bottom right of the active WhatsApp chat",
            "the latest sent message bubble in the current WhatsApp conversation",
            "the most recent message you sent in the active WhatsApp chat",
        )

    def _whatsapp_chat_preview_descriptions(self, contact: str) -> tuple[str, ...]:
        return (
            f"the selected WhatsApp chat preview for {contact} in the left chats list",
            f"the left chat list row for {contact} showing the latest message preview",
        )

    def _screen_region_contains_message(self, screen_interact, descriptions: tuple[str, ...], message: str) -> bool:
        for description in descriptions:
            try:
                text = screen_interact.read_element(description)
            except Exception:
                continue
            if text and not text.startswith("[") and self._ui_text_contains_message(text, message):
                return True
        return False

    def _screen_region_texts(self, screen_interact, descriptions: tuple[str, ...]) -> list[str]:
        texts: list[str] = []
        for description in descriptions:
            try:
                text = screen_interact.read_element(description)
            except Exception:
                continue
            if text and not text.startswith("["):
                texts.append(" ".join(str(text).split()))
        return texts

    def _detect_whatsapp_blocked_state(self, screen_interact) -> str:
        blocked_tokens = (
            "unblock",
            "delete chat",
            "delete conversation",
            "block this chat",
        )
        for text in self._screen_region_texts(screen_interact, self._whatsapp_blocked_state_descriptions()):
            normalized = self._normalize_ui_text(text)
            if any(token in normalized for token in blocked_tokens):
                return text
        return ""

    def _screen_action_without_extra_prompt(self, screen_interact, method_name: str, *args, **kwargs):
        method = getattr(screen_interact, method_name)
        original_ask = getattr(screen_interact, "_ask_permission", None)
        if not callable(original_ask):
            return method(*args, **kwargs)
        try:
            screen_interact._ask_permission = lambda description, x, y, action: True
            return method(*args, **kwargs)
        finally:
            screen_interact._ask_permission = original_ask

    def _clean_whatsapp_candidate_label(self, label: str) -> str:
        cleaned = " ".join((label or "").replace("\n", " ").split())
        cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", cleaned)
        return cleaned.strip()

    def _is_plausible_whatsapp_title(self, alias: str, title: str) -> bool:
        cleaned_alias = self._clean_whatsapp_candidate_label(alias)
        cleaned_title = self._clean_whatsapp_candidate_label(title)
        if not cleaned_title:
            return False
        alias_tokens = self._tokenize_ui_text(cleaned_alias)
        title_tokens = self._tokenize_ui_text(cleaned_title)
        if alias_tokens and not any(token in title_tokens for token in alias_tokens):
            return False
        if len("".join(title_tokens)) <= 3 and self._normalize_ui_text(cleaned_title) != self._normalize_ui_text(cleaned_alias):
            return False
        return True

    def _read_whatsapp_active_chat_title(self, expected_contact: str = "") -> str:
        screen_interact = getattr(self.jarvis, "screen_interact", None)
        if not screen_interact:
            return ""
        descriptions = (
            "the active WhatsApp chat title at the top of the conversation",
            "the contact name at the top center of the current WhatsApp chat",
            "the conversation header title in WhatsApp",
        )
        expected_tokens = self._tokenize_ui_text(expected_contact)
        fallback = ""
        for description in descriptions:
            try:
                text = screen_interact.read_element(description)
            except Exception:
                continue
            cleaned = self._clean_whatsapp_candidate_label(text)
            if not cleaned or cleaned.startswith("["):
                continue
            fallback = fallback or cleaned
            if expected_tokens:
                label_tokens = self._tokenize_ui_text(cleaned)
                if any(token in label_tokens for token in expected_tokens):
                    return cleaned
        return fallback

    def _find_whatsapp_candidates(self, search_query: str) -> list[dict]:
        screen_interact = getattr(self.jarvis, "screen_interact", None)
        if not screen_interact:
            return []

        query_tokens = self._tokenize_ui_text(search_query)
        descriptions = (
            f"all visible WhatsApp search results in the left panel matching '{search_query}'",
            f"all visible WhatsApp contacts or chats whose title contains '{search_query}' in the left panel",
            f"all selectable contact results for '{search_query}' in the WhatsApp new chat panel",
        )

        deduped: dict[str, dict] = {}
        for description in descriptions:
            try:
                raw_results = screen_interact.find_all_elements(description)
            except Exception:
                continue
            for item in raw_results or []:
                label = self._clean_whatsapp_candidate_label(str(item.get("label", "")))
                if not label:
                    continue
                norm_label = self._normalize_ui_text(label)
                if query_tokens and not any(token in norm_label for token in query_tokens):
                    continue
                deduped.setdefault(norm_label, {
                    "label": label,
                    "x": int(item.get("x", 0)),
                    "y": int(item.get("y", 0)),
                })
            if deduped:
                break
        return list(deduped.values())[:6]

    def _resolve_whatsapp_candidate(self, search_query: str, alias: str = "") -> dict:
        candidates = self._find_whatsapp_candidates(search_query)
        if not candidates:
            cleaned_query = self._clean_whatsapp_candidate_label(alias or search_query)
            query_tokens = self._tokenize_ui_text(cleaned_query)
            if len(query_tokens) <= 1:
                return {"kind": "needs_specific_contact"}
            return {"kind": "keyboard"}

        preferred = self.get_contact(alias or search_query, "whatsapp") or search_query
        preferred_norm = self._normalize_ui_text(preferred)
        query_norm = self._normalize_ui_text(search_query)
        preferred_tokens = self._tokenize_ui_text(preferred)
        query_tokens = self._tokenize_ui_text(search_query)

        def score(candidate: dict) -> int:
            label_norm = self._normalize_ui_text(candidate.get("label", ""))
            score_value = 0
            if preferred_norm and label_norm == preferred_norm:
                score_value += 8
            elif preferred_norm and preferred_norm in label_norm:
                score_value += 6
            if preferred_tokens and all(token in label_norm for token in preferred_tokens):
                score_value += 4
            if query_norm and label_norm == query_norm:
                score_value += 3
            elif query_norm and query_norm in label_norm:
                score_value += 2
            if query_tokens and all(token in label_norm for token in query_tokens):
                score_value += 2
            return score_value

        scored = sorted(candidates, key=score, reverse=True)
        if len(scored) == 1:
            return {"kind": "click", "candidate": scored[0]}

        best_score = score(scored[0])
        second_score = score(scored[1]) if len(scored) > 1 else -1
        if best_score >= 6 and best_score > second_score:
            return {"kind": "click", "candidate": scored[0]}

        options = [candidate["label"] for candidate in scored]
        return {"kind": "ambiguous", "options": options}

    def _send_whatsapp(self, contact: str, message: str, alias: str | None = None) -> dict:
        """
        WhatsApp Desktop flow:
          1. Open app via URI scheme (fallback: WhatsApp Web)
          2. Search for contact (Ctrl+F)
          3. Select contact from results (click first result)
          4. Wait for chat to open, click the message input box
          5. Type and send message
        """
        try:
            # 1 - Open WhatsApp
            if not self._open_app("whatsapp"):
                return {"success": False, "message": "Could not open WhatsApp. Is it installed?"}

            if not self._wait_for_window("WhatsApp", timeout=10):
                # Fallback to web
                self._open_web_fallback("whatsapp")
                time.sleep(4)

            time.sleep(2)

            # 2 - Start a fresh new-chat search. This is more reliable on
            # WhatsApp Desktop than generic Ctrl+F, which can leave focus in
            # the wrong left-panel search field.
            pyautogui.hotkey("ctrl", "n")
            time.sleep(0.8)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("backspace")
            time.sleep(0.1)
            self._type_text_safe(contact)
            time.sleep(2)  # wait for search results to appear

            # 3 - Select first result — press DOWN then ENTER
            #     (DOWN moves focus from search bar to the result list)
            selected_contact = contact
            selection = self._resolve_whatsapp_candidate(contact, alias or contact)
            if selection.get("kind") == "needs_specific_contact":
                return {
                    "success": False,
                    "message": f"I couldn't safely choose the right WhatsApp result for {alias or contact}. Please say the full visible contact name."
                }
            if selection.get("kind") == "ambiguous":
                options = selection.get("options", [])[:4]
                options_text = "; ".join(f"{idx + 1}. {item}" for idx, item in enumerate(options))
                return {
                    "success": False,
                    "message": f"I found multiple WhatsApp matches for {alias or contact}: {options_text}. Which one should I use?",
                    "data": {
                        "kind": "ambiguous_contact",
                        "options": options,
                        "query": alias or contact,
                        "selected_contact": selected_contact or contact,
                    },
                }
            if selection.get("kind") == "click" and selection.get("candidate"):
                candidate = selection["candidate"]
                pyautogui.click(int(candidate["x"]), int(candidate["y"]))
                selected_contact = candidate.get("label") or contact
            else:
                pyautogui.press("down")
                time.sleep(0.3)
                pyautogui.press("enter")
            time.sleep(1.5)  # wait for chat to fully open

            exact_title = self._read_whatsapp_active_chat_title(selected_contact or contact)
            if exact_title:
                if self._is_plausible_whatsapp_title(alias or contact, exact_title):
                    selected_contact = exact_title
                else:
                    return {
                        "success": False,
                        "message": f"I searched WhatsApp for {alias or contact}, but it stayed on {exact_title} instead of opening the right chat."
                    }

            screen_interact = getattr(self.jarvis, "screen_interact", None)
            composer_descriptions = self._whatsapp_composer_descriptions()
            def focus_and_type_message() -> bool:
                focused_input = False
                typed_via_screen = False
                self._wait_for_window("WhatsApp", timeout=3)
                if screen_interact:
                    for description in composer_descriptions:
                        try:
                            type_result = self._screen_action_without_extra_prompt(
                                screen_interact,
                                "type_into_element",
                                description,
                                message,
                            )
                            if type_result and type_result.get("success"):
                                focused_input = True
                                typed_via_screen = True
                                break
                        except Exception:
                            continue

                    if not typed_via_screen:
                        for description in composer_descriptions:
                            try:
                                click_result = self._screen_action_without_extra_prompt(
                                    screen_interact,
                                    "click_element",
                                    description,
                                )
                                if click_result and click_result.get("success"):
                                    time.sleep(0.6)
                                    focused_input = True
                                    break
                            except Exception:
                                continue

                if not focused_input:
                    # Fall back to tab navigation instead of Escape.
                    for _ in range(4):
                        pyautogui.press("tab")
                        time.sleep(0.2)
                    focused_input = True

                if not typed_via_screen:
                    self._wait_for_window("WhatsApp", timeout=3)
                    self._type_text_safe(message)
                    time.sleep(0.3)

                return typed_via_screen

            # 4 - Focus the composer and place the message text.
            typed_via_screen = focus_and_type_message()

            if screen_interact and self._screen_region_contains_message(
                screen_interact,
                self._whatsapp_wrong_panel_descriptions(),
                message,
            ):
                # Recover once: clear the wrong field, close the left panel,
                # then retry the composer focus path.
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)
                pyautogui.press("escape")
                time.sleep(0.5)

                typed_via_screen = focus_and_type_message()

                if screen_interact and self._screen_region_contains_message(
                    screen_interact,
                    self._whatsapp_wrong_panel_descriptions(),
                    message,
                ):
                    return {
                        "success": False,
                        "message": f"I opened {selected_contact or contact}'s chat, but the text kept landing in the left sidebar instead of the chat composer."
                    }

            if screen_interact:
                blocked_state = self._detect_whatsapp_blocked_state(screen_interact)
                if blocked_state:
                    return {
                        "success": False,
                        "message": f"I opened {selected_contact or contact}'s chat, but WhatsApp is showing chat actions like Unblock/Delete chat instead of a usable message box."
                    }

            self._wait_for_window("WhatsApp", timeout=3)
            pyautogui.press("enter")
            time.sleep(1.0)

            # 6 - Verify: confirm the message actually appeared in the chat.
            verified = False
            composer_still_has_message = False
            try:
                if hasattr(self.jarvis, "screen_interact"):
                    blocked_state = self._detect_whatsapp_blocked_state(self.jarvis.screen_interact)
                    if blocked_state:
                        return {
                            "success": False,
                            "message": f"I opened {selected_contact or contact}'s chat, but WhatsApp is showing chat actions like Unblock/Delete chat instead of a usable message box."
                        }

                    verified = self._screen_region_contains_message(
                        self.jarvis.screen_interact,
                        self._whatsapp_sent_message_descriptions(),
                        message,
                    ) or self._screen_region_contains_message(
                        self.jarvis.screen_interact,
                        self._whatsapp_chat_preview_descriptions(selected_contact or contact),
                        message,
                    )

                    composer_still_has_message = self._screen_region_contains_message(
                        self.jarvis.screen_interact,
                        composer_descriptions,
                        message,
                    )

                    if not verified and self._screen_region_contains_message(
                        self.jarvis.screen_interact,
                        self._whatsapp_wrong_panel_descriptions(),
                        message,
                    ):
                        return {
                            "success": False,
                            "message": f"I opened {selected_contact or contact}'s chat, but the text stayed in the left sidebar instead of the chat composer."
                        }
            except Exception:
                pass  # vision not available — report honestly

            if verified:
                return {"success": True, "message": f"Message sent to {selected_contact or contact} on WhatsApp. Verified.", "data": {"selected_contact": selected_contact or contact}}
            if composer_still_has_message:
                return {
                    "success": False,
                    "message": f"I opened {selected_contact or contact}'s chat, but the text is still sitting in the message box, so it was not sent."
                }
            return {
                "success": False,
                "message": f"I opened {selected_contact or contact}'s chat and pressed Enter, but I couldn't verify the message appeared. I stopped so I don't send a duplicate."
            }

        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return {"success": False, "message": f"WhatsApp error: {e}"}

    def _send_telegram(self, contact: str, message: str) -> dict:
        """
        Telegram Desktop flow:
          1. Open app via URI scheme
          2. Search (Ctrl+K)
          3. Select contact from results
          4. Wait for chat to open — cursor auto-focuses message input
          5. Type and send
        """
        try:
            if not self._open_app("telegram"):
                return {"success": False, "message": "Could not open Telegram. Is it installed?"}

            if not self._wait_for_window("Telegram", timeout=10):
                self._open_web_fallback("telegram")
                time.sleep(4)

            time.sleep(2)

            # Search
            pyautogui.press("escape")
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.8)
            self._type_text_safe(contact)
            time.sleep(2)

            # Select first result
            pyautogui.press("down")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(1.5)  # wait for chat to fully open

            # Telegram auto-focuses the message input after opening a chat
            # but press Escape first to close search overlay if still open
            pyautogui.press("escape")
            time.sleep(0.5)

            # Type and send
            self._type_text_safe(message)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)

            return {"success": True, "message": f"Message sent to {contact} on Telegram."}

        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return {"success": False, "message": f"Telegram error: {e}"}

    def _send_instagram(self, contact: str, message: str) -> dict:
        """
        Instagram DM flow (web-based):
          1. Open instagram.com/direct/inbox
          2. Click compose / search
          3. Find contact
          4. Type and send
        """
        try:
            self._open_web_fallback("instagram")
            time.sleep(5)

            # Click the pencil / new-message icon (top-right of DM panel)
            # Use keyboard shortcut or tab navigation
            pyautogui.hotkey("tab")
            time.sleep(0.5)

            # Search for contact
            self._type_text_safe(contact)
            time.sleep(2)

            # Select first result
            pyautogui.press("enter")
            time.sleep(1)

            # Click "Chat" or "Next" button
            pyautogui.press("tab")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(1)

            # Type message
            self._type_text_safe(message)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)

            return {"success": True, "message": f"DM sent to {contact} on Instagram."}

        except Exception as e:
            logger.error(f"Instagram send failed: {e}")
            return {"success": False, "message": f"Instagram error: {e}"}

    def _send_discord(self, contact: str, message: str) -> dict:
        """
        Discord Desktop flow:
          1. Open Discord
          2. Ctrl+K to open quick-switcher
          3. Search for user
          4. Open DM, type, send
        """
        try:
            if not self._open_app("discord"):
                return {"success": False, "message": "Could not open Discord. Is it installed?"}

            if not self._wait_for_window("Discord", timeout=10):
                self._open_web_fallback("discord")
                time.sleep(4)

            time.sleep(2)

            # Quick switcher
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.5)
            self._type_text_safe(contact)
            time.sleep(1.5)

            # Select first result
            pyautogui.press("enter")
            time.sleep(1.5)

            # Type and send
            self._type_text_safe(message)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)

            return {"success": True, "message": f"DM sent to {contact} on Discord."}

        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return {"success": False, "message": f"Discord error: {e}"}

    def _send_generic(self, app_name: str, contact: str, message: str) -> dict:
        """
        Generic approach for any messaging app:
          1. Try to open via URI or start menu
          2. Use Ctrl+F or Ctrl+K to search
          3. Type contact, enter, type message, enter
        """
        try:
            if not self._open_app(app_name):
                return {"success": False, "message": f"Could not open {app_name}."}

            time.sleep(3)

            # Try common search shortcuts
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.5)
            self._type_text_safe(contact)
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(1)

            self._type_text_safe(message)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)

            return {"success": True, "message": f"Message sent to {contact} on {app_name}."}

        except Exception as e:
            logger.error(f"Generic send ({app_name}) failed: {e}")
            return {"success": False, "message": f"{app_name} error: {e}"}

    # ── Contact book ──────────────────────────────────────────

    def _load_contacts(self) -> dict:
        """Load contacts from ~/.jarvis_contacts.json"""
        try:
            if CONTACTS_FILE.exists():
                with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load contacts: {e}")
        return {}

    def _save_contacts(self):
        """Persist contacts to disk."""
        try:
            with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.contacts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save contacts: {e}")

    def add_contact(self, name: str, app: str, identifier: str):
        """Add or update a contact mapping."""
        key = name.lower()
        exact_title = str(identifier or "").strip()
        if not exact_title:
            return
        if app.lower() == "whatsapp" and not self._is_plausible_whatsapp_title(name, exact_title):
            logger.info("Skipping WhatsApp contact learning for '%s' -> '%s' because the title looks incomplete", name, exact_title)
            return
        if key not in self.contacts:
            self.contacts[key] = {}
        self.contacts[key][app.lower()] = {
            "query": exact_title,
            "exact_title": exact_title,
        }
        self._save_contacts()

    def get_contact(self, name: str, app: str) -> str | None:
        """Look up a contact identifier for a specific app."""
        entry = self.contacts.get(name.lower(), {})
        value = entry.get(app.lower())
        if isinstance(value, dict):
            return value.get("exact_title") or value.get("query")
        return value

    # ── Message queue ─────────────────────────────────────────

    def queue_message(self, app: str, contact: str, message: str):
        """Queue a message for later delivery."""
        with self._queue_lock:
            self.message_queue.append({
                "app": app,
                "contact": contact,
                "message": message,
                "queued_at": time.time(),
            })
        self._reply(f"Message queued -- will send when {app.title()} is ready.")
        logger.info(f"Message queued for {contact} on {app}")

    def process_queue(self) -> list[dict]:
        """Attempt to send all queued messages. Returns results."""
        results = []
        with self._queue_lock:
            remaining = []
            for item in self.message_queue:
                result = self.send_message(item["app"], item["contact"], item["message"])
                if result["success"]:
                    results.append(result)
                else:
                    remaining.append(item)
            self.message_queue = remaining
        return results

    # ── PyAutoGUI automation helpers ──────────────────────────

    def _open_app(self, app_name: str) -> bool:
        """
        Open a messaging app by name.
        Uses Windows URI schemes first, then falls back to start menu search.
        """
        app_key = app_name.lower()
        uri = APP_URI_MAP.get(app_key)

        try:
            if uri:
                subprocess.Popen(f"start {uri}", shell=True)
                time.sleep(2)
                return True

            # Fallback: try opening via Windows start menu search
            pyautogui.hotkey("win")
            time.sleep(0.5)
            self._type_text_safe(app_name)
            time.sleep(1)
            pyautogui.press("enter")
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Failed to open {app_name}: {e}")
            return False

    def _open_web_fallback(self, app_name: str):
        """Open the web version of an app in the default browser."""
        url = APP_WEB_FALLBACKS.get(app_name.lower())
        if url:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception as e:
                logger.error(f"Could not open {url}: {e}")

    def _wait_for_window(self, title_substring: str, timeout: int = 10) -> bool:
        """
        Wait for a window with the given title substring to appear.
        Uses pyautogui's window detection on Windows.
        """
        try:
            import pygetwindow as gw
        except ImportError:
            # Without pygetwindow, just wait and hope
            time.sleep(3)
            return True

        deadline = time.time() + timeout
        while time.time() < deadline:
            windows = gw.getWindowsWithTitle(title_substring)
            if windows:
                try:
                    win = windows[0]
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                except Exception:
                    pass
                return True
            time.sleep(0.5)

        logger.warning(f"Window '{title_substring}' not found within {timeout}s")
        return False

    def _type_text_safe(self, text: str):
        """
        Type text, handling non-ASCII characters via clipboard paste.
        Falls back to pyautogui.write() for ASCII-only text.
        """
        if text.isascii() and HAS_PYAUTOGUI:
            pyautogui.write(text, interval=0.02)
            return

        # Use clipboard for non-ASCII or as primary method
        if HAS_PYPERCLIP:
            pyperclip.copy(text)
        else:
            # Fallback: use subprocess to set clipboard on Windows
            try:
                process = subprocess.Popen(
                    ["clip"], stdin=subprocess.PIPE, shell=True
                )
                process.communicate(text.encode("utf-16le"))
            except Exception as e:
                logger.error(f"Clipboard fallback failed: {e}")
                # Last resort: type only ASCII portion
                pyautogui.write(text.encode("ascii", errors="ignore").decode(), interval=0.02)
                return

        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)

    def _press_key(self, key: str):
        """Press a single key with a small delay."""
        pyautogui.press(key)
        time.sleep(0.15)

    def _find_and_click(self, description: str):
        """
        Try to find and click a UI element.
        If screen_interact (AI element finder) is available via JARVIS, use it.
        Otherwise fall back to keyboard shortcuts.
        """
        if hasattr(self.jarvis, "screen_interact"):
            try:
                self.jarvis.screen_interact.click(description)
                return
            except Exception:
                pass
        logger.debug(f"Could not find element: {description} -- using keyboard fallback")

    # ── Thread management ─────────────────────────────────────

    def _send_in_thread(self, app: str, contact: str, message: str):
        """Run the send operation in a background thread."""
        def _worker():
            result = self.send_message(app, contact, message)
            if result["success"]:
                self._reply(result["message"])
            else:
                self._reply(f"Failed: {result['message']}")

        thread = threading.Thread(target=_worker, daemon=True, name="jarvis-msg-send")
        thread.start()

    # ── UI helper ─────────────────────────────────────────────

    def _reply(self, text: str):
        """Send a message to the JARVIS chat UI."""
        try:
            self.jarvis.chat.add_message("assistant", text)
        except Exception:
            print(f"[messaging] {text}")
