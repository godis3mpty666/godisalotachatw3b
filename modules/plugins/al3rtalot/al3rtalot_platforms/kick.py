from __future__ import annotations

from typing import Any

from .base import BaseAlertPlatform


class KickAlerts(BaseAlertPlatform):
    platform = "kick"
    label = "Kick"
    default_color = "#53fc18"

    # Nur Kick erweitert: Twitch, TikTok und YouTube bleiben unverändert.
    # Die offiziellen Kick Events/Webhooks liefern Namen wie channel.followed
    # oder channel.subscription.gifts. al3rtalot zeigt nur interne Alerttypen an,
    # deshalb werden diese Namen hier Kick-spezifisch normalisiert.
    supported_events = ("chat", "join", "follow", "subscribe", "gift", "raid", "live_status")

    _official_event_aliases = {
        "channel.followed": "follow",
        "channel_followed": "follow",
        "channelfollowed": "follow",
        "follow.created": "follow",
        "follow_created": "follow",

        "channel.subscription.new": "subscribe",
        "channel_subscription_new": "subscribe",
        "subscription.new": "subscribe",
        "subscription_new": "subscribe",
        "new.subscription": "subscribe",
        "new_subscription": "subscribe",

        "channel.subscription.renewal": "subscribe",
        "channel_subscription_renewal": "subscribe",
        "subscription.renewal": "subscribe",
        "subscription_renewal": "subscribe",
        "subscription.renewed": "subscribe",
        "subscription_renewed": "subscribe",
        "resub": "subscribe",
        "resubscribe": "subscribe",

        "channel.subscription.gifts": "gift",
        "channel_subscription_gifts": "gift",
        "subscription.gifts": "gift",
        "subscription_gifts": "gift",
        "gifted.subscriptions": "gift",
        "gifted_subscriptions": "gift",
        "gifted.subscription": "gift",
        "gifted_subscription": "gift",

        "kicks.gifted": "gift",
        "kicks_gifted": "gift",
        "kick.gifted": "gift",
        "kick_gifted": "gift",

        "raid": "raid",
        "raid.created": "raid",
        "raid_created": "raid",
        "channel.raid": "raid",
        "channel_raid": "raid",

        "livestream.status.updated": "live_status",
        "livestream_status_updated": "live_status",
        "stream.status.updated": "live_status",
        "stream_status_updated": "live_status",

        "user.joined": "join",
        "user_joined": "join",
        "chatroom.user.joined": "join",
        "chatroom_user_joined": "join",
        "viewer.joined": "join",
        "viewer_joined": "join",
    }

    def normalize_event(self, msg: Any) -> dict[str, Any] | None:
        if not isinstance(msg, dict):
            return None

        raw_platform = str(msg.get("platform") or msg.get("source_platform") or "").strip().lower()
        if raw_platform != self.platform:
            return None

        raw_event_type = str(
            msg.get("event_type")
            or msg.get("alert_type")
            or msg.get("alert_kind")
            or msg.get("type")
            or msg.get("message_type")
            or "chat"
        ).strip().lower()
        if raw_event_type.startswith("kick_"):
            raw_event_type = raw_event_type[5:]

        mapped_event_type = self._official_event_aliases.get(raw_event_type, raw_event_type)
        enhanced = dict(msg)
        enhanced["event_type"] = mapped_event_type

        payload = self._payload_dict(msg)

        if not str(enhanced.get("username") or enhanced.get("display_name") or enhanced.get("user") or enhanced.get("author") or "").strip():
            name = self._first_name(
                payload,
                ("user", "follower", "sender", "subscriber", "gifter", "recipient", "broadcaster", "channel"),
            )
            if name:
                enhanced["username"] = name

        if not str(enhanced.get("text") or enhanced.get("message") or enhanced.get("content") or "").strip():
            text = self._first_text(payload)
            if text:
                enhanced["text"] = text

        if enhanced.get("amount") in (None, "", 0, "0"):
            amount = self._first_amount(payload)
            if amount is not None:
                enhanced["amount"] = amount

        if not isinstance(enhanced.get("raw"), dict):
            enhanced["raw"] = payload if payload else dict(msg)

        return super().normalize_event(enhanced)

    def _payload_dict(self, msg: dict[str, Any]) -> dict[str, Any]:
        for key in ("raw", "data", "payload", "event"):
            value = msg.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _first_name(self, payload: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                for name_key in ("username", "display_name", "name", "slug", "login"):
                    raw = str(value.get(name_key) or "").strip()
                    if raw:
                        return raw
            elif isinstance(value, str) and value.strip() and key in {"user", "sender", "follower"}:
                return value.strip()

        for name_key in ("username", "display_name", "user_name", "sender_username", "follower_username"):
            raw = str(payload.get(name_key) or "").strip()
            if raw:
                return raw
        return ""

    def _first_text(self, payload: dict[str, Any]) -> str:
        for key in ("message", "content", "text", "title"):
            raw = str(payload.get(key) or "").strip()
            if raw:
                return raw
        return ""

    def _first_amount(self, payload: dict[str, Any]) -> int | None:
        for key in ("amount", "count", "quantity", "total", "gift_count", "gifted_subscriptions", "kicks", "coins"):
            raw = payload.get(key)
            if raw not in (None, ""):
                try:
                    return int(float(str(raw).strip()))
                except Exception:
                    continue
        return None
