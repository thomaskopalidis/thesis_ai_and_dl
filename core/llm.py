from __future__ import annotations

import requests
import json
import os
import config

CLOUD_PROVIDER = os.getenv("CLOUD_LLM_PROVIDER", "")   # "openai" or "anthropic"
CLOUD_API_KEY  = os.getenv("CLOUD_LLM_API_KEY", "")
CLOUD_MODEL    = os.getenv("CLOUD_LLM_MODEL", "gpt-4o-mini")

# How many full exchanges to keep before summarising
HISTORY_WINDOW = 10
# Summarise when history exceeds this many exchanges
SUMMARY_THRESHOLD = 10


def list_ollama_models() -> list[str]:
    """Return names of models available in the local Ollama server."""
    try:
        resp = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        if resp.ok:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return [config.OLLAMA_MODEL]


def _ollama_chat(messages: list, stream: bool = True, max_tokens: int = 50, model: str | None = None):
    """Low-level call to Ollama. Yields text tokens when stream=True, returns full text when False."""
    payload = {
        "model": model or config.OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"num_predict": max_tokens, "temperature": 0.3, "num_ctx": 2048},
        "keep_alive": "30m",
    }
    # First-token load can take minutes if the model file sits on slow storage
    # (Google Drive mount). (connect_timeout, read_timeout) decouples the two.
    timeout = (10, int(os.getenv("OLLAMA_READ_TIMEOUT", "300")))
    try:
        response = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json=payload,
            stream=stream,
            timeout=timeout,
        )
        if not response.ok:
            print(f"   ✗ Ollama error: {response.status_code} - {response.text}")
            if stream:
                yield "I encountered an error with my text engine."
            else:
                return "Error."
            return

        if stream:
            for line in response.iter_lines():
                if line:
                    body = json.loads(line)
                    content = body.get("message", {}).get("content", "")
                    if content:
                        yield content
        else:
            full = ""
            for line in response.iter_lines():
                if line:
                    body = json.loads(line)
                    full += body.get("message", {}).get("content", "")
            return full

    except requests.exceptions.ConnectionError:
        msg = "I cannot reach my language model right now. Please make sure Ollama is running (ollama serve)."
        print(f"   ✗ Ollama offline: {config.OLLAMA_URL}")
        if stream:
            yield msg
        else:
            return msg
    except Exception as e:
        msg = "I am having trouble connecting to my brain right now."
        print(f"   ✗ LLM Exception: {e}")
        if stream:
            yield msg
        else:
            return msg


def _summarise_history(history: list) -> str:
    """Asks the LLM to compress the conversation history into a short paragraph."""
    formatted = "\n".join(
        f"{'Student' if m['role'] == 'user' else 'Teacher'}: {m['content']}"
        for m in history
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. Summarise the following physics tutoring "
                "conversation in 2-3 sentences, preserving key topics and formulas discussed."
            ),
        },
        {"role": "user", "content": f"Conversation to summarise:\n{formatted}"},
    ]
    summary = ""
    for token in _ollama_chat(messages, stream=True, max_tokens=120):
        summary += token
    print(f"[HISTORY] Summarised {len(history)} exchanges into: {summary[:80]}...")
    return summary.strip()


class ConversationHistory:
    """Manages per-session message history with automatic summarisation."""

    def __init__(self):
        self._exchanges: list[dict] = []   # list of {role, content}
        self._summary: str = ""            # rolling summary of older exchanges

    def add(self, role: str, content: str):
        self._exchanges.append({"role": role, "content": content})
        if len(self._exchanges) >= SUMMARY_THRESHOLD * 2:  # *2 because each exchange = 2 messages
            self._compress()

    def _compress(self):
        to_summarise = self._exchanges[: HISTORY_WINDOW * 2]
        new_summary = _summarise_history(to_summarise)
        if self._summary:
            self._summary = f"{self._summary} Later: {new_summary}"
        else:
            self._summary = new_summary
        self._exchanges = self._exchanges[HISTORY_WINDOW * 2 :]
        print(f"[HISTORY] Compressed. Kept {len(self._exchanges)} recent messages.")

    def build_messages(self, system_prompt: str, new_user_message: str) -> list:
        """Assembles the full message list to send to Ollama."""
        system = system_prompt
        if self._summary:
            system += f"\n\nConversation summary so far:\n{self._summary}"

        messages = [{"role": "system", "content": system}]
        messages.extend(self._exchanges)
        messages.append({"role": "user", "content": new_user_message})
        return messages

    def clear(self):
        self._exchanges = []
        self._summary = ""

    @property
    def exchange_count(self) -> int:
        return len(self._exchanges) // 2


SYSTEM_PROMPT = (
    "You are an expert Physics teacher. Answer concisely in 1-2 sentences max. "
    "Always include the key formula when relevant (e.g., F=ma). Use simple language suitable for students. "
    "No lists, no markdown formatting. Speak naturally. "
    "Remember the conversation context and refer back to earlier topics when relevant."
)


def _resolve_cloud(model: str | None) -> tuple[str, str, str]:
    """
    Parse `model` string of the form 'cloud:<provider>:<model_name>' and
    return (provider, model_name, api_key).

    Supported providers: openai, anthropic, google (gemini), deepseek, xai (grok)

    API keys are looked up per-provider from environment:
      OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, XAI_API_KEY

    Falls back to legacy CLOUD_LLM_* env vars if `model` not in the new format.
    """
    if model and model.startswith("cloud:"):
        parts = model.split(":", 2)
        if len(parts) == 3:
            _, provider, model_name = parts
        else:
            # cloud:provider  → use default model for that provider
            _, provider = parts
            model_name = {
                "openai": "gpt-4o-mini",
                "anthropic": "claude-haiku-4-5",
                "google": "gemini-3.5-flash",
                "deepseek": "deepseek-chat",
                "xai": "grok-code-fast-1",
            }.get(provider, "")
    else:
        provider = (CLOUD_PROVIDER or "openai").lower()
        model_name = CLOUD_MODEL

    key_env = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "xai": "XAI_API_KEY",
    }.get(provider, "CLOUD_LLM_API_KEY")

    api_key = os.getenv(key_env) or CLOUD_API_KEY
    return provider, model_name, api_key


def _cloud_chat(messages: list, max_tokens: int = 80, model: str | None = None):
    """Yields text tokens from a cloud LLM. Routes by provider parsed from `model`."""
    provider, model_name, api_key = _resolve_cloud(model)

    if not api_key:
        yield f"Cloud API key not configured for provider '{provider}'."
        return

    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    chat_msgs = [m for m in messages if m["role"] != "system"]

    try:
        if provider == "anthropic":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "system": system_msg,
                    "messages": chat_msgs,
                },
                timeout=60,
            )
            if resp.ok:
                yield resp.json()["content"][0]["text"]
            else:
                yield f"Cloud error ({provider}): {resp.status_code} {resp.text[:200]}"

        elif provider == "google":
            # Gemini uses a different schema: {contents: [{parts: [{text: ...}], role: ...}]}
            # System prompt is passed as systemInstruction.
            contents = []
            for m in chat_msgs:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            payload = {
                "contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }
            if system_msg:
                payload["systemInstruction"] = {"parts": [{"text": system_msg}]}
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                json=payload,
                timeout=60,
            )
            if resp.ok:
                data = resp.json()
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    yield text
                except (KeyError, IndexError):
                    yield f"Cloud error ({provider}): unexpected response {str(data)[:200]}"
            else:
                yield f"Cloud error ({provider}): {resp.status_code} {resp.text[:200]}"

        elif provider == "deepseek":
            # DeepSeek is OpenAI-compatible
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                json={"model": model_name, "messages": messages, "max_tokens": max_tokens, "stream": False},
                timeout=60,
            )
            if resp.ok:
                yield resp.json()["choices"][0]["message"]["content"]
            else:
                yield f"Cloud error ({provider}): {resp.status_code} {resp.text[:200]}"

        elif provider == "xai":
            # xAI Grok is also OpenAI-compatible
            resp = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                json={"model": model_name, "messages": messages, "max_tokens": max_tokens, "stream": False},
                timeout=60,
            )
            if resp.ok:
                yield resp.json()["choices"][0]["message"]["content"]
            else:
                yield f"Cloud error ({provider}): {resp.status_code} {resp.text[:200]}"

        else:
            # OpenAI (default)
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                json={"model": model_name, "messages": messages, "max_tokens": max_tokens, "stream": False},
                timeout=60,
            )
            if resp.ok:
                yield resp.json()["choices"][0]["message"]["content"]
            else:
                yield f"Cloud error ({provider}): {resp.status_code} {resp.text[:200]}"

    except Exception as e:
        yield f"Cloud error ({provider}): {type(e).__name__}: {e}"


def stream_llm_response(prompt: str, history: "ConversationHistory | None" = None, context: str = "", model: str | None = None):
    """Streams LLM response tokens. Updates history in-place if provided."""
    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nUse this knowledge base context when relevant:\n{context}"

    if history is not None:
        messages = history.build_messages(system, prompt)
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

    use_cloud = (model or "").startswith("cloud:")
    full_response = ""

    if use_cloud:
        for token in _cloud_chat(messages, max_tokens=80, model=model):
            full_response += token
            yield token
    else:
        for token in _ollama_chat(messages, stream=True, max_tokens=80, model=model):
            full_response += token
            yield token

    # Record the exchange after streaming completes
    if history is not None and full_response:
        history.add("user", prompt)
        history.add("assistant", full_response)
