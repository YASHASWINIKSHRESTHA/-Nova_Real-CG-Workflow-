import base64
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client: Optional[OpenAI] = None

# Cost per 1M tokens (USD)
_COST = {
    "gpt-4o":       {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini":  {"input": 0.15,  "output": 0.60},
}


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set — copy .env.example to .env and add your key")
        _client = OpenAI(api_key=api_key)
    return _client


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rates = _COST.get(model, {"input": 0.0, "output": 0.0})
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000


def _log(model: str, tokens_in: int, tokens_out: int, cost: float) -> None:
    print(f"[llm] model={model} in={tokens_in} out={tokens_out} cost=${cost:.6f}")


def call_vision(images: list[str | bytes], prompt: str) -> tuple[str, float]:
    """Call GPT-4o with one or more images (file paths or raw PNG/JPEG bytes). Returns (raw_text, cost_usd)."""
    model = "gpt-4o"
    content: list[dict] = [{"type": "text", "text": prompt}]

    for img in images:
        if isinstance(img, bytes):
            raw = img
            media_type = "image/png"
        else:
            raw = Path(img).read_bytes()
            suffix = Path(img).suffix.lower()
            media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
        b64 = base64.b64encode(raw).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "high"},
        })

    resp = _get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=4096,
    )
    tokens_in = resp.usage.prompt_tokens
    tokens_out = resp.usage.completion_tokens
    cost = _calc_cost(model, tokens_in, tokens_out)
    _log(model, tokens_in, tokens_out, cost)
    return resp.choices[0].message.content, cost


def call_text(
    prompt: str,
    system: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[str] = None,
) -> tuple[str, float]:
    """Call GPT-4o-mini for text tasks. Returns (raw_text_or_json, cost_usd)."""
    model = "gpt-4o-mini"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict = {"model": model, "messages": messages, "max_tokens": 2048}
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    resp = _get_client().chat.completions.create(**kwargs)
    tokens_in = resp.usage.prompt_tokens
    tokens_out = resp.usage.completion_tokens
    cost = _calc_cost(model, tokens_in, tokens_out)
    _log(model, tokens_in, tokens_out, cost)

    choice = resp.choices[0]
    # Check tool_calls presence directly — finish_reason may be "stop" even when
    # tool_choice forces a function call, leaving content as None.
    if choice.message.tool_calls:
        return choice.message.tool_calls[0].function.arguments, cost

    return choice.message.content or "", cost


def parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON from an LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first and last fence lines
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    return json.loads(text)
