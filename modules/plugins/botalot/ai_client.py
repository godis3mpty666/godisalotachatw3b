from __future__ import annotations

import json
import urllib.error
import urllib.request

from common import strip_response, to_int


class OpenAIChatClient:
    def __init__(self, logger) -> None:
        self._log = logger

    def _is_responses_model(self, model: str) -> bool:
        m = (model or "").lower().strip()
        return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4")

    def _use_hosted_prompt(self, settings: dict) -> bool:
        return bool(str(settings.get("openai_prompt_id") or "").strip())

    def _prompt_ref(self, settings: dict) -> dict:
        ref = {"id": str(settings.get("openai_prompt_id") or "").strip()}
        version = str(settings.get("openai_prompt_version") or "").strip()
        if version.lower().startswith("v") and version[1:].isdigit():
            version = version[1:]
        if version:
            ref["version"] = version
        return ref

    def _prompt_label(self, settings: dict) -> str:
        ref = self._prompt_ref(settings)
        version = ref.get("version")
        return f"hosted_prompt={ref.get('id')}" + (f":{version}" if version else "")

    def _post_json(self, url: str, api_key: str, payload: dict, timeout: int) -> dict:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw or "{}")

    def _extract_text(self, payload: dict) -> str:
        text = payload.get("output_text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                for block in item.get("content") or []:
                    if isinstance(block, dict) and isinstance(block.get("text"), str) and block.get("text", "").strip():
                        parts.append(block["text"].strip())
            if parts:
                return " ".join(parts).strip()
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content") if isinstance(message, dict) else ""
            if isinstance(content, str):
                return content.strip()
        return ""

    def _error_message(self, exc: urllib.error.HTTPError, label: str = "") -> str:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        suffix = f" ({label})" if label else ""
        if exc.code == 401:
            return "OpenAI Fehler 401: API-Key ungueltig oder nicht berechtigt."
        if exc.code == 404:
            extra = f": {detail}" if detail else ""
            return f"OpenAI Fehler 404{suffix}: Modell/Prompt nicht verfuegbar oder falscher Endpoint{extra}"
        return f"OpenAI HTTP {exc.code}: {detail}".strip()

    def test_connection(self, settings: dict) -> tuple[bool, str]:
        api_key = str(settings.get("openai_api_key") or "").strip()
        if not api_key:
            return False, "OpenAI API-Key fehlt im Core."
        model = str(settings.get("openai_model") or "gpt-5-mini").strip() or "gpt-5-mini"
        try:
            label = self._prompt_label(settings) if self._use_hosted_prompt(settings) else f"model={model}"
            if self._use_hosted_prompt(settings):
                payload = {"prompt": self._prompt_ref(settings), "input": "Connection test. Antworte kurz mit OK.", "max_output_tokens": 80}
                data = self._post_json("https://api.openai.com/v1/responses", api_key, payload, 15)
            elif self._is_responses_model(model):
                payload = {"model": model, "instructions": "Antworte exakt mit OK.", "input": "Sag nur OK", "max_output_tokens": 64}
                if model.lower().startswith("gpt-5"):
                    payload["reasoning"] = {"effort": "minimal"}
                data = self._post_json("https://api.openai.com/v1/responses", api_key, payload, 15)
            else:
                payload = {"model": model, "messages": [{"role": "system", "content": "Antworte exakt mit OK."}, {"role": "user", "content": "Sag nur OK"}], "max_tokens": 20}
                data = self._post_json("https://api.openai.com/v1/chat/completions", api_key, payload, 15)
            text = self._extract_text(data)
            return (bool(text), f"OpenAI verbunden: {label}, response={text[:40]}" if text else f"OpenAI verbunden, aber ohne Textausgabe: {label}")
        except urllib.error.HTTPError as exc:
            return False, self._error_message(exc, label)
        except Exception as exc:
            return False, f"OpenAI Netzwerk/API Fehler: {exc}"

    def generate(self, settings: dict, source_platform: str, username: str, text: str, reason: str, context_text: str) -> str:
        api_key = str(settings.get("openai_api_key") or "").strip()
        if not api_key:
            self._log("OpenAI API-Key fehlt im Core. Keine Antwort erzeugt.")
            return ""
        model = str(settings.get("openai_model") or "gpt-5-mini").strip() or "gpt-5-mini"
        max_chars = to_int(settings.get("max_response_chars"), 200, 40, 500)
        custom_prompt = str(settings.get("custom_system_prompt") or settings.get("base_system_prompt") or "").strip()
        fallback_prompt = custom_prompt or "Du bist botalot. Antworte kurz, direkt, hilfreich und menschlich."
        runtime_rules = f"Trigger: {reason}. Plattform: {source_platform}. Nutzer: {username}. Antworte maximal {max_chars} Zeichen."
        use_hosted_prompt = self._use_hosted_prompt(settings)
        instructions = "" if use_hosted_prompt else f"{fallback_prompt}\n\n{runtime_rules}"
        input_text = runtime_rules + "\n\nLetzte Nachrichten dieses Nutzers:\n" + (context_text or "(keine)") + f"\n\nAktuell: {text}"
        max_tokens = max(60, min(260, max_chars * 2))
        label = self._prompt_label(settings) if use_hosted_prompt else f"model={model}"
        try:
            if use_hosted_prompt:
                payload = {"prompt": self._prompt_ref(settings), "input": input_text, "max_output_tokens": max_tokens}
                data = self._post_json("https://api.openai.com/v1/responses", api_key, payload, 20)
            elif self._is_responses_model(model):
                payload = {"model": model, "input": input_text, "max_output_tokens": max_tokens}
                if instructions:
                    payload["instructions"] = instructions
                if model.lower().startswith("gpt-5"):
                    payload["reasoning"] = {"effort": "minimal"}
                data = self._post_json("https://api.openai.com/v1/responses", api_key, payload, 20)
            else:
                payload = {"model": model, "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": input_text}], "max_tokens": max_tokens}
                data = self._post_json("https://api.openai.com/v1/chat/completions", api_key, payload, 20)
            return strip_response(self._extract_text(data), max_chars)
        except urllib.error.HTTPError as exc:
            self._log(self._error_message(exc, label))
        except Exception as exc:
            self._log(f"OpenAI Fehler: {exc}")
        return ""
