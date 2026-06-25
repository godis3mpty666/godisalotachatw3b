from __future__ import annotations

from typing import Any

from al3rtalot_common import as_bool, clean_name, clean_text, render_template, split_names, to_int


class BaseAlertPlatform:
    platform = "base"
    label = "Base"
    default_color = "#ff2d55"
    supported_events = ("chat",)

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    def enabled(self, settings: dict[str, Any]) -> bool:
        return as_bool(settings.get(f"{self.platform}_enabled"), True)

    def ignored_users(self, settings: dict[str, Any]) -> set[str]:
        global_names = split_names(settings.get("ignored_users"))
        platform_names = split_names(settings.get(f"{self.platform}_ignored_users"))
        return global_names | platform_names

    def event_enabled(self, settings: dict[str, Any], event_type: str) -> bool:
        key = f"{self.platform}_enable_{event_type}"
        if key in settings:
            return as_bool(settings.get(key), True)
        return event_type in self.supported_events

    def normalize_event(self, msg: Any) -> dict[str, Any] | None:
        if not isinstance(msg, dict):
            return None
        raw_platform = clean_text(msg.get("platform") or msg.get("source_platform") or "").lower()
        if raw_platform != self.platform:
            return None
        event_type = clean_text(
            msg.get("event_type")
            or msg.get("alert_type")
            or msg.get("alert_kind")
            or msg.get("type")
            or msg.get("message_type")
            or "chat"
        ).lower()
        if event_type.startswith(self.platform + "_"):
            event_type = event_type[len(self.platform) + 1:]
        event_aliases = {
            # normaler Chat darf im Alertplugin nicht versehentlich als Alert landen.
            # Die Chat-Integrationen markieren normalen Chat inzwischen als chat_no_alert.
            "chat_no_alert": "chat_no_alert",
            "message_no_alert": "chat_no_alert",
            "comment_no_alert": "chat_no_alert",

            "message": "chat",
            "comment": "chat",

            "follower": "follow",
            "new_follow": "follow",
            "new_follower": "follow",
            "followed": "follow",

            "sub": "subscribe",
            "subscription": "subscribe",
            "subscriber": "subscribe",
            "new_subscriber": "subscribe",
            "new_subscription": "subscribe",
            "resub": "subscribe",
            "resubscribe": "subscribe",

            "member": "member",
            "membership": "member",
            "new_member": "member",
            "sponsor": "member",
            "new_sponsor": "member",
            "member_milestone": "member",

            "viewer_join": "join",
            "viewer_joined": "join",
            "user_join": "join",
            "user_joined": "join",
            "joiner": "join",
            "joined": "join",
            "chat_join": "join",
            "chat_joined": "join",

            "likes": "like",
            "gifted_likes": "like",
            "like_count": "like",

            "gifts": "gift",
            "gifted": "gift",
            "gift_sub": "gift",
            "gift_subs": "gift",
            "gifted_sub": "gift",
            "gifted_subs": "gift",
            "subscription_gift": "gift",

            "shares": "share",
            "shared": "share",

            "super_chat": "superchat",
            "super-chat": "superchat",
            "super_chat_event": "superchat",
            "superchat_event": "superchat",

            "super_sticker": "supersticker",
            "super-sticker": "supersticker",
            "supersticker_event": "supersticker",
            "super_sticker_event": "supersticker",

            "donate": "donation",
            "donated": "donation",
            "tip": "donation",
            "cheer": "bits",
            "bit": "bits",
        }
        event_type = event_aliases.get(event_type, event_type)
        if event_type in {"message", "comment"}:
            event_type = "chat"
        username = clean_name(msg.get("username") or msg.get("display_name") or msg.get("user") or msg.get("author") or "")
        text = clean_text(msg.get("text") or msg.get("message") or msg.get("content") or "")
        amount = to_int(
            msg.get("amount")
            or msg.get("count")
            or msg.get("alert_count")
            or msg.get("event_count")
            or msg.get("increment")
            or msg.get("likes")
            or 0,
            0,
            0,
        )
        gift_name = clean_text(msg.get("gift_name") or msg.get("giftName") or msg.get("gift") or "")
        raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
        return {
            "platform": self.platform,
            "event_type": event_type,
            "username": username,
            "text": text,
            "amount": amount,
            "gift_name": gift_name,
            "channel": clean_text(msg.get("channel") or ""),
            "message_id": clean_text(msg.get("message_id") or msg.get("id") or ""),
            "raw": raw,
        }

    def should_alert(self, event: dict[str, Any], settings: dict[str, Any]) -> bool:
        if not self.enabled(settings):
            return False
        event_type = clean_text(event.get("event_type") or "chat").lower()
        if event_type == "chat_no_alert":
            return False
        if event_type not in self.supported_events:
            return False
        if not self.event_enabled(settings, event_type):
            return False
        username = clean_name(event.get("username")).lower()
        if username and username in self.ignored_users(settings):
            return False
        if event_type == "chat" and not clean_text(event.get("text")):
            return False
        return True

    def build_alert(self, event: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        event_type = clean_text(event.get("event_type") or "chat").lower()
        template = settings.get(f"{self.platform}_{event_type}_template") or settings.get(f"{event_type}_template") or "{user}: {text}"
        user = clean_name(event.get("username")) or "Unbekannt"
        text = clean_text(event.get("text"))
        amount = to_int(event.get("amount"), 0, 0)
        data = {
            "platform": self.label,
            "platform_id": self.platform,
            "event": event_type,
            "event_label": event_type.title(),
            "user": user,
            "text": text,
            "amount": amount,
            "gift_name": clean_text(event.get("gift_name")),
            "channel": clean_text(event.get("channel")),
        }
        line = render_template(template, data)
        title_template = settings.get(f"{self.platform}_{event_type}_title") or settings.get(f"{event_type}_title") or "{event_label}"
        title = render_template(title_template, data)
        return {
            "platform": self.platform,
            "event_type": event_type,
            "username": user,
            "title": title,
            "text": line,
            "amount": amount,
            "color": settings.get(f"{self.platform}_accent_color") or self.default_color,
            "channel": clean_text(event.get("channel")),
            "message_id": clean_text(event.get("message_id")),
            "raw": event.get("raw") if isinstance(event.get("raw"), dict) else {},
        }
