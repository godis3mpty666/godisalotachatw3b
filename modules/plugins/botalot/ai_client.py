from __future__ import annotations
import json
import urllib.error
import urllib.request
from common import strip_response, to_int


class OpenAIChatClient:
    def __init__(self, logger) -> None:
        self._log = logger

    def _is_responses_model(self, model: str) -> bool:
        m = (model or '').lower().strip()
        return m.startswith('gpt-5') or m.startswith('o1') or m.startswith('o3') or m.startswith('o4')

    def _use_hosted_prompt(self, settings: dict) -> bool:
        val = settings.get('use_openai_hosted_prompt')
        if isinstance(val, bool):
            enabled = val
        else:
            enabled = str(val or '').strip().lower() in {'1', 'true', 'yes', 'ja', 'on'}
        return enabled and bool(str(settings.get('openai_prompt_id') or '').strip())

    def _prompt_ref(self, settings: dict) -> dict:
        ref = {'id': str(settings.get('openai_prompt_id') or '').strip()}
        version = str(settings.get('openai_prompt_version') or '').strip()
        if version:
            ref['version'] = version
        return ref

    def _post_json(self, url: str, api_key: str, payload: dict, timeout: int) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        try:
            return json.loads(raw)
        except Exception:
            return {'_raw': raw}

    def _extract_text(self, obj: dict) -> str:
        # Responses API convenience field
        text = obj.get('output_text')
        if isinstance(text, str) and text.strip():
            return text.strip()

        # Responses API nested output[].content[].text
        output = obj.get('output')
        if isinstance(output, list):
            parts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get('content')
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            t = block.get('text')
                            if isinstance(t, str) and t.strip():
                                parts.append(t.strip())
                # Some APIs may put text directly on message-like items
                t = item.get('text')
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
            if parts:
                return ' '.join(parts).strip()

        # Chat Completions legacy output
        choices = obj.get('choices')
        if isinstance(choices, list) and choices:
            msg = choices[0].get('message', {}) if isinstance(choices[0], dict) else {}
            content = msg.get('content') if isinstance(msg, dict) else ''
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        t = block.get('text') or block.get('content')
                        if isinstance(t, str) and t.strip():
                            parts.append(t.strip())
                if parts:
                    return ' '.join(parts).strip()
        return ''

    def _openai_error_message(self, exc: urllib.error.HTTPError) -> str:
        detail = exc.read().decode('utf-8', errors='replace')[:900]
        if exc.code == 401:
            return 'OpenAI Fehler 401: API Key ungültig oder nicht berechtigt.'
        if exc.code == 404:
            return 'OpenAI Fehler 404: Modell nicht verfügbar oder kein Zugriff auf das Modell.'
        return f'OpenAI HTTP Fehler {exc.code}: {detail}'

    def _responses_payload(self, model: str, instructions: str, input_text: str, max_tokens: int) -> dict:
        payload = {
            'model': model,
            'instructions': instructions,
            'input': input_text,
            'max_output_tokens': max_tokens,
        }
        # GPT-5 reasoning can burn tiny test token budgets without producing text.
        # Minimal keeps the connection test and stream replies short/cheap.
        if model.lower().startswith('gpt-5'):
            payload['reasoning'] = {'effort': 'minimal'}
        return payload

    def _chat_payload(self, model: str, messages: list[dict], max_tokens: int) -> dict:
        payload = {'model': model, 'messages': messages}
        # Newer chat/reasoning models reject max_tokens.
        if self._is_responses_model(model):
            payload['max_completion_tokens'] = max_tokens
        else:
            payload['max_tokens'] = max_tokens
        return payload

    def test_connection(self, settings: dict) -> tuple[bool, str]:
        api_key = str(settings.get('openai_api_key') or '').strip()
        if not api_key:
            return False, 'OpenAI API Key fehlt.'
        model = str(settings.get('openai_model') or 'gpt-5-mini').strip() or 'gpt-5-mini'
        try:
            if self._use_hosted_prompt(settings):
                payload = {
                    'prompt': self._prompt_ref(settings),
                    'input': 'Connection test. Antworte kurz mit OK.',
                    'max_output_tokens': 80,
                }
                obj = self._post_json('https://api.openai.com/v1/responses', api_key, payload, 14)
            elif self._is_responses_model(model):
                payload = self._responses_payload(model, 'Antworte exakt mit OK.', 'Sag nur OK', 64)
                obj = self._post_json('https://api.openai.com/v1/responses', api_key, payload, 14)
            else:
                payload = self._chat_payload(model, [
                    {'role': 'system', 'content': 'Antworte exakt mit OK.'},
                    {'role': 'user', 'content': 'Sag nur OK'},
                ], 20)
                obj = self._post_json('https://api.openai.com/v1/chat/completions', api_key, payload, 14)
            content = self._extract_text(obj)
            if content:
                if self._use_hosted_prompt(settings):
                    return True, f'OpenAI verbunden: hosted_prompt={settings.get("openai_prompt_id")}, response={content[:40]}'
                return True, f'OpenAI verbunden: model={model}, response={content[:40]}'
            status = obj.get('status', 'unknown')
            incomplete = obj.get('incomplete_details') or obj.get('error') or ''
            return False, f'OpenAI verbunden, aber keine Textausgabe: model={model}, status={status}, details={incomplete}'
        except urllib.error.HTTPError as exc:
            return False, self._openai_error_message(exc)
        except Exception as exc:
            return False, f'OpenAI Netzwerk/API Fehler: {exc}'

    def generate(self, settings: dict, source_platform: str, username: str, text: str, reason: str, context_text: str) -> str:
        api_key = str(settings.get('openai_api_key') or '').strip()
        if not api_key:
            self._log('OpenAI API Key fehlt. Keine AI-Antwort erzeugt.')
            return ''
        model = str(settings.get('openai_model') or 'gpt-5-mini').strip() or 'gpt-5-mini'
        max_chars = to_int(settings.get('max_response_chars'), 200, 40, 500)
        system_prompt = str(settings.get('system_prompt') or '').strip()
        if not system_prompt:
            system_prompt = 'Du bist botalot. Antworte kurz, lustig, hilfreich und nicht wiederholend.'
        trigger_hint = ''
        if str(reason).lower().startswith('ursula'):
            trigger_hint = '\nDiese aktuelle Nachricht ist ein Ursula-Trigger. Sprich direkt den Schreiber an und mach klar, dass er Mr. Streamer damit nicht nerven soll.'
        else:
            trigger_hint = '\nDiese aktuelle Nachricht ist KEIN Ursula-Trigger. Erwähne Ursula NICHT, außer die aktuelle Nachricht fragt ausdrücklich danach.'
        instructions = system_prompt + f'\n\nAktueller Trigger: {reason}. Antworte maximal {max_chars} Zeichen. Aktuelle Plattform: {source_platform}. Zuschauer: {username}.{trigger_hint}'
        input_text = 'Letzte Nachrichten NUR von diesem Chatter auf dieser Plattform:\n' + (context_text or '(keine)') + '\n\nAntworte jetzt auf diese aktuelle Nachricht:\n' + f'[{source_platform}] {username}: {text}'
        max_tokens = max(60, min(260, max_chars * 2))
        try:
            if self._use_hosted_prompt(settings):
                hosted_input = instructions + '\\n\\n' + input_text
                payload = {
                    'prompt': self._prompt_ref(settings),
                    'input': hosted_input,
                    'max_output_tokens': max_tokens,
                }
                obj = self._post_json('https://api.openai.com/v1/responses', api_key, payload, 18)
            elif self._is_responses_model(model):
                payload = self._responses_payload(model, instructions, input_text, max_tokens)
                obj = self._post_json('https://api.openai.com/v1/responses', api_key, payload, 18)
            else:
                payload = self._chat_payload(model, [
                    {'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': input_text},
                ], max_tokens)
                obj = self._post_json('https://api.openai.com/v1/chat/completions', api_key, payload, 18)
            content = self._extract_text(obj)
            if not content:
                self._log(f'OpenAI lieferte keine Textausgabe. status={obj.get("status", "unknown")}, details={obj.get("incomplete_details") or obj.get("error") or ""}')
                return ''
            return strip_response(content, max_chars)
        except urllib.error.HTTPError as exc:
            self._log(self._openai_error_message(exc))
        except Exception as exc:
            self._log(f'OpenAI Fehler: {exc}')
        return ''
