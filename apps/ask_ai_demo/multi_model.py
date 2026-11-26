"""
Multi-provider support for Ask AI demo.

Providers:  openai (default, handled by chat_agent.run_chat_agent), gemini, claude.

Gemini / Claude agents mirror run_chat_agent():
    - async generators yielding SSE strings
    - fill `result` (text, finish, files, searches, sources) and `text_sink`
    - web search (Gemini google_search grounding / Claude web_search tool)
    - document generation through the same run_python_code sandbox tool
Image and video generation are intentionally NOT offered.
"""
import asyncio
import base64
import json
import logging
import re

from django.conf import settings

from .chat_agent import MAX_STEPS, RUN_PYTHON_TOOL, _handle_code_call
from .sse_events import ERROR, TOOL_CALL, sse, sse_token

logger = logging.getLogger(__name__)

PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_CLAUDE = "claude"
ALL_PROVIDERS = (PROVIDER_OPENAI, PROVIDER_GEMINI, PROVIDER_CLAUDE)
DEFAULT_PROVIDER = PROVIDER_OPENAI

_ALIASES = {
    "openai": PROVIDER_OPENAI, "chatgpt": PROVIDER_OPENAI, "gpt": PROVIDER_OPENAI,
    "gemini": PROVIDER_GEMINI, "google": PROVIDER_GEMINI,
    "claude": PROVIDER_CLAUDE, "anthropic": PROVIDER_CLAUDE,
}


# --------------------------------------------------------------------------
# Selection helpers
# --------------------------------------------------------------------------
def gemini_uses_openai() -> bool:
    """When True, route Gemini requests through the ChatGPT/Azure OpenAI key with a distinct Gemini style."""
    return bool(getattr(settings, "GEMINI_USE_OPENAI_KEY", True))


def provider_key(provider):
    if provider == PROVIDER_GEMINI:
        if gemini_uses_openai():
            return getattr(settings, "AZURE_OPENAI_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None) or None
        return getattr(settings, "GEMINI_API_KEY", None)
    if provider == PROVIDER_CLAUDE:
        return getattr(settings, "ANTHROPIC_API_KEY", None)
    return getattr(settings, "AZURE_OPENAI_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None) or None


def provider_model_name(provider):
    if provider == PROVIDER_GEMINI:
        return getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
    if provider == PROVIDER_CLAUDE:
        return getattr(settings, "CLAUDE_MODEL", "claude-sonnet-4-6")
    from .openai_client import get_chat_model
    return get_chat_model()


def provider_available(provider):
    if provider == PROVIDER_OPENAI or (provider == PROVIDER_GEMINI and gemini_uses_openai()):
        from .openai_client import is_azure_openai
        import os
        return bool(is_azure_openai() or provider_key(PROVIDER_OPENAI) or os.environ.get("OPENAI_API_KEY"))
    return bool(provider_key(provider))


def list_providers():
    from .openai_client import is_azure_openai
    openai_label = "ChatGPT (Azure OpenAI)" if is_azure_openai() else "ChatGPT (OpenAI)"
    labels = {PROVIDER_OPENAI: openai_label, PROVIDER_GEMINI: "Gemini (Google)", PROVIDER_CLAUDE: "Claude (Anthropic)"}
    return [
        {
            "id": p,
            "label": labels[p],
            "model": provider_model_name(p),
            "available": provider_available(p),
            "default": p == DEFAULT_PROVIDER,
        }
        for p in ALL_PROVIDERS
    ]


def parse_models(data):
    """
    Read the user's choice from request data. Accepts `models` / `model` as a list,
    repeated form fields, a JSON list string or a comma separated string.
    Returns (selected, skipped). Empty / invalid selection -> default OpenAI.
    """
    raw = []
    for key in ("models", "model", "providers"):
        if hasattr(data, "getlist"):
            vals = data.getlist(key)
        else:
            v = data.get(key) if hasattr(data, "get") else None
            vals = v if isinstance(v, (list, tuple)) else ([v] if v else [])
        raw.extend(vals)

    names = []
    for item in raw:
        if isinstance(item, str):
            item = item.strip()
            if item.startswith("["):
                try:
                    names.extend(json.loads(item))
                    continue
                except ValueError:
                    pass
            names.extend(re.split(r"[,\s]+", item))
        elif item:
            names.append(str(item))

    selected, skipped = [], []
    for n in names:
        p = _ALIASES.get(str(n).strip().lower())
        if not p or p in selected or p in skipped:
            continue
        (selected if provider_available(p) else skipped).append(p)

    if not selected:
        selected = [DEFAULT_PROVIDER]
    return selected, skipped


# --------------------------------------------------------------------------
# Streams: tag every SSE event with its model, and merge several streams
# --------------------------------------------------------------------------
def tag_event(ev, model):
    try:
        head, data = ev.split("\ndata: ", 1)
        payload = json.loads(data.strip())
        if isinstance(payload, dict):
            payload["model"] = model
        return f"{head}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception:
        return ev


async def merge_streams(generators):
    """Run several async generators concurrently and yield their events as they arrive."""
    queue = asyncio.Queue()

    async def pump(gen):
        try:
            async for ev in gen:
                await queue.put(ev)
        except Exception as exc:  # one model failing must not kill the others
            logger.exception("Model stream failed: %s", exc)
            await queue.put(sse(ERROR, {"message": str(exc)}))
        finally:
            await queue.put(None)

    tasks = [asyncio.create_task(pump(g)) for g in generators]
    finished = 0
    try:
        while finished < len(tasks):
            ev = await queue.get()
            if ev is None:
                finished += 1
            else:
                yield ev
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _split_data_uri(url):
    m = re.match(r"data:([^;]+);base64,(.*)", url or "", re.S)
    return (m.group(1), m.group(2)) if m else (None, None)


def _text_of(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text"))


def _code_call(args):
    return {"arguments": json.dumps(args)}


# --------------------------------------------------------------------------
# Claude
# --------------------------------------------------------------------------
def _to_claude_messages(messages):
    system, out = "", []
    for i, m in enumerate(messages):
        role, content = m.get("role"), m.get("content")
        if role == "system":
            system += (_text_of(content) + "\n\n")
            continue
        role = "assistant" if role == "assistant" else "user"
        blocks = []
        if isinstance(content, list):
            for p in content:
                t = p.get("type") if isinstance(p, dict) else None
                if t in ("text", "input_text", "output_text") and p.get("text"):
                    blocks.append({"type": "text", "text": p["text"]})
                elif t == "image_url":
                    img = p.get("image_url")
                    url = img.get("url") if isinstance(img, dict) else img
                    mime, b64 = _split_data_uri(url)
                    if b64:
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
        elif content:
            blocks.append({"type": "text", "text": str(content)})
        if not blocks:
            continue
        if out and out[-1]["role"] == role:          # Claude needs alternating roles
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "Hello"}]})
    return system.strip(), out


async def run_claude_agent(*, messages, load_input_files, sandbox_url, save_file, result, text_sink,
                           allow_tools=True, web_search=True, max_tool_calls=3, temperature=0.7,
                           max_tokens=8000, **_):
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        yield sse(ERROR, {"message": "Claude support is not installed on the server (pip install anthropic)."})
        return

    ws_id = getattr(settings, "ANTHROPIC_WORKSPACE_ID", None)
    default_headers = {"anthropic-workspace-id": ws_id} if ws_id else None
    client = AsyncAnthropic(api_key=provider_key(PROVIDER_CLAUDE), default_headers=default_headers)
    system, msgs = _to_claude_messages(messages)
    result.update(text="", files=[], finish=None, searches=[], sources=[])

    tools = []
    if allow_tools:
        tools.append({
            "name": RUN_PYTHON_TOOL["name"],
            "description": RUN_PYTHON_TOOL["description"],
            "input_schema": {k: v for k, v in RUN_PYTHON_TOOL["parameters"].items() if k != "additionalProperties"},
        })
    if web_search:
        tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": int(max_tool_calls or 3)})

    st = {"fix_rounds": 0, "file_saved": False}
    for step in range(MAX_STEPS):
        kw = dict(model=provider_model_name(PROVIDER_CLAUDE), max_tokens=max_tokens,
                  messages=msgs)
        if system:
            kw["system"] = system
        if tools:
            kw["tools"] = tools
            if st["file_saved"]:
                kw["tool_choice"] = {"type": "none"}

        async with client.messages.stream(**kw) as stream:
            async for ev in stream:
                et = getattr(ev, "type", None)
                if et == "text":
                    text_sink.append(ev.text)
                    result["text"] += ev.text
                    yield sse_token(ev.text)
                elif et == "content_block_start":
                    block = ev.content_block
                    if block.type == "tool_use":
                        yield sse(TOOL_CALL, {"name": block.name, "message": "✍️ Writing Python code…"})
                    elif block.type == "server_tool_use":
                        yield sse(TOOL_CALL, {"name": "web_search", "message": "🔎 Searching the web…"})
            final = await stream.get_final_message()

        blocks = list(final.content or [])
        for b in blocks:
            if b.type == "server_tool_use":
                q = (getattr(b, "input", None) or {}).get("query")
                if q:
                    result["searches"].append(q)
            elif b.type == "text":
                for c in (getattr(b, "citations", None) or []):
                    url = getattr(c, "url", None)
                    if url and url not in [s["url"] for s in result["sources"]]:
                        result["sources"].append({"url": url, "title": getattr(c, "title", None)})

        result["finish"] = "length" if final.stop_reason == "max_tokens" else "stop"
        assistant_blocks = [b.model_dump(exclude_none=True) for b in blocks]

        if final.stop_reason == "pause_turn":
            msgs.append({"role": "assistant", "content": assistant_blocks})
            continue

        calls = [b for b in blocks if b.type == "tool_use"]
        if not calls:
            return

        ctx = {"load_input_files": load_input_files, "sandbox_url": sandbox_url, "save_file": save_file,
               "result": result, "finish": result["finish"], "step": step}
        tool_results = []
        for call in calls:
            box = {}
            if call.name == "run_python_code":
                async for ev in _handle_code_call(_code_call(call.input), st, ctx, box):
                    yield ev
            else:
                box["output"] = f"Unknown tool '{call.name}'."
            tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": box.get("output") or ""})
        msgs.append({"role": "assistant", "content": assistant_blocks})
        msgs.append({"role": "user", "content": tool_results})

    yield sse(ERROR, {"message": "⚠️ Stopped after too many steps without finishing."})


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------
def _to_gemini(messages, types):
    system, contents = "", []
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            system += (_text_of(content) + "\n\n")
            continue
        grole = "model" if role == "assistant" else "user"
        parts = []
        if isinstance(content, list):
            for p in content:
                t = p.get("type") if isinstance(p, dict) else None
                if t in ("text", "input_text", "output_text") and p.get("text"):
                    parts.append(types.Part.from_text(text=p["text"]))
                elif t == "image_url":
                    img = p.get("image_url")
                    url = img.get("url") if isinstance(img, dict) else img
                    mime, b64 = _split_data_uri(url)
                    if b64:
                        parts.append(types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime))
        elif content:
            parts.append(types.Part.from_text(text=str(content)))
        if not parts:
            continue
        if contents and contents[-1].role == grole:
            contents[-1].parts.extend(parts)
        else:
            contents.append(types.Content(role=grole, parts=parts))
    if not contents or contents[0].role != "user":
        contents.insert(0, types.Content(role="user", parts=[types.Part.from_text(text="Hello")]))
    return system.strip(), contents


def prepare_messages_for_provider(messages, provider):
    """
    Build a clean, API-safe copy of `messages` tailored for `provider`:
    - When a past turn has multiple side-by-side assistant answers (compare mode),
      keep only this provider's own answer (or the first one if this provider did
      not answer that turn) so models do not confuse each other's identities.
    - Strip internal metadata keys (keys starting with '_') before sending to APIs.
    """
    out = []
    i = 0
    n = len(messages)
    while i < n:
        m = messages[i]
        if m.get("role") != "assistant":
            out.append({k: v for k, v in m.items() if not k.startswith("_")})
            i += 1
            continue

        # Collect consecutive assistant messages belonging to the same turn
        group = []
        while i < n and messages[i].get("role") == "assistant":
            group.append(messages[i])
            i += 1

        chosen = next((g for g in group if g.get("_provider") == provider), group[0])
        out.append({k: v for k, v in chosen.items() if not k.startswith("_")})
    return out


def _append_system_directive(messages, directive):
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "system" and isinstance(m.get("content"), str):
            m["content"] = m["content"] + "\n\n" + directive
            return out
    out.insert(0, {"role": "system", "content": directive})
    return out


def build_openai_messages(messages):
    """Attach ChatGPT's crisp, structured identity & style without mutating `messages`."""
    directive = (
        "IDENTITY & STYLE (ChatGPT):\n"
        "- You are ChatGPT, an AI assistant. If asked who you are, identify yourself as ChatGPT.\n"
        "- Communicate in a crisp, direct, pragmatic, structured style: lead with a clear answer, "
        "use clean numbered steps or tight bullets, and prioritize actionable clarity."
    )
    return _append_system_directive(messages, directive)


def _build_gemini_openai_messages(messages, intent="general"):
    """Build a non-mutating copy of messages with a distinct Gemini identity, analytical lens, and format."""
    gemini_directive = (
        "CRITICAL — YOU ARE GEMINI (DISTINCT ANALYTICAL LENS & FORMAT):\n"
        "1. IDENTITY: You are Gemini. If asked who you are or which model you are, identify yourself "
        "as Gemini (never ChatGPT, GPT, Claude, or OpenAI).\n"
        "2. ACCURACY FIRST: For factual lookups, math, code, or document-grounded questions, be 100% "
        "accurate — while explaining with your own clear, intuitive voice and practical context.\n"
        "3. DISTINCT ANGLE (for advice, lists, ideas, strategy, summaries, and tips):\n"
        "   - Think from a behavioral, systems-design, metrics, and growth/execution angle rather than "
        "giving the most generic surface-level textbook points.\n"
        "   - Deliberately skip the obvious #1 cliché answer and offer sharper, more specific, "
        "high-leverage insights backed by a quick real-world example or scenario.\n"
        "4. DISTINCT FORMAT:\n"
        "   - Open with a bold 1-line core insight (never start with 'Sure!', 'Certainly!', or a plain "
        "echo of the user's title like '### Three Ways to...').\n"
        "   - For multi-point answers, use bullet points (`- **Bold Angle** — concise explanation + "
        "concrete example`) instead of plain numbered lists, and close with a 1-line **Bottom Line:**.\n"
        "   - For single-sentence or brief prompts, keep it equally brief, punchy, and unconventional.\n"
    )
    if intent == "document_generation":
        gemini_directive += (
            "5. DOCUMENT / PPTX STYLE: Use a distinct creative narrative, unique real-world examples, "
            "a modern Indigo/Violet/Teal palette (Deep Indigo RGBColor(24,24,66), Electric Violet "
            "RGBColor(124,58,237), Teal RGBColor(20,184,166)), and include 'Gemini' in the filename.\n"
        )

    out = [dict(m) for m in messages]
    # Insert right before the final user message so recency attention enforces the distinct voice/format
    insert_idx = len(out) - 1 if out and out[-1].get("role") == "user" else len(out)
    out.insert(insert_idx, {"role": "system", "content": gemini_directive})
    return out


async def run_gemini_agent(*, messages, load_input_files, sandbox_url, save_file, result, text_sink,
                           allow_tools=True, web_search=True, max_tool_calls=3, intent="general",
                           temperature=0.7, max_tokens=8000, **_):
    if gemini_uses_openai():
        from .chat_agent import run_chat_agent
        from .openai_client import get_async_openai_client, get_chat_model, is_azure_openai

        gemini_messages = _build_gemini_openai_messages(messages, intent=intent)
        base_temp = 0.7 if temperature is None else float(temperature)
        gemini_temp = min(1.0, round(base_temp + 0.25, 2))
        base_kwargs = {
            "model": get_chat_model(),
            "max_output_tokens": max_tokens,
            "temperature": gemini_temp,
        }
        if is_azure_openai():
            base_kwargs["presence_penalty"] = 0.75
            base_kwargs["frequency_penalty"] = 0.45

        async for ev in run_chat_agent(
            client=get_async_openai_client(),
            base_kwargs=base_kwargs,
            messages=gemini_messages,
            load_input_files=load_input_files,
            sandbox_url=sandbox_url,
            save_file=save_file,
            result=result,
            text_sink=text_sink,
            allow_tools=allow_tools,
            web_search=web_search,
            web_search_options=getattr(settings, "WEB_SEARCH_OPTIONS", None),
            max_tool_calls=max_tool_calls,
            store=getattr(settings, "OPENAI_STORE_RESPONSES", False),
        ):
            yield ev
        return

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        yield sse(ERROR, {"message": "Gemini support is not installed on the server (pip install google-genai)."})
        return

    client = genai.Client(api_key=provider_key(PROVIDER_GEMINI))
    system, contents = _to_gemini(messages, types)
    result.update(text="", files=[], finish=None, searches=[], sources=[])

    # Gemini cannot mix google_search with function calling in one request,
    # so: document requests -> code tool, everything else -> web search grounding.
    use_code = allow_tools and intent == "document_generation"
    tools = None
    if use_code:
        params = {k: v for k, v in RUN_PYTHON_TOOL["parameters"].items() if k != "additionalProperties"}
        tools = [types.Tool(function_declarations=[types.FunctionDeclaration(
            name=RUN_PYTHON_TOOL["name"], description=RUN_PYTHON_TOOL["description"], parameters=params)])]
    elif web_search:
        tools = [types.Tool(google_search=types.GoogleSearch())]

    st = {"fix_rounds": 0, "file_saved": False}
    for step in range(MAX_STEPS):
        cfg = types.GenerateContentConfig(
            system_instruction=system or None, temperature=temperature,
            max_output_tokens=max_tokens, tools=None if st["file_saved"] else tools,
        )
        calls, call_parts, finish = [], [], "stop"
        stream = await client.aio.models.generate_content_stream(
            model=provider_model_name(PROVIDER_GEMINI), contents=contents, config=cfg)
        async for chunk in stream:
            cand = chunk.candidates[0] if chunk.candidates else None
            if cand is None:
                continue
            for part in (cand.content.parts if cand.content and cand.content.parts else []):
                if getattr(part, "function_call", None):
                    calls.append(part.function_call)
                    call_parts.append(part)
                    yield sse(TOOL_CALL, {"name": part.function_call.name, "message": "✍️ Writing Python code…"})
                elif getattr(part, "text", None) and not getattr(part, "thought", False):
                    text_sink.append(part.text)
                    result["text"] += part.text
                    yield sse_token(part.text)
            if cand.finish_reason is not None and "MAX_TOKENS" in str(cand.finish_reason):
                finish = "length"
            gm = getattr(cand, "grounding_metadata", None)
            if gm:
                for q in (gm.web_search_queries or []):
                    if q not in result["searches"]:
                        result["searches"].append(q)
                        yield sse(TOOL_CALL, {"name": "web_search", "message": "🔎 Searching the web…"})
                for gc in (gm.grounding_chunks or []):
                    web = getattr(gc, "web", None)
                    if web and web.uri and web.uri not in [s["url"] for s in result["sources"]]:
                        result["sources"].append({"url": web.uri, "title": web.title})
        result["finish"] = finish

        if not calls:
            if result["sources"]:
                extra = "\n\n**Sources**\n" + "\n".join(
                    f"- [{s['title'] or s['url']}]({s['url']})" for s in result["sources"][:8])
                result["text"] += extra
                text_sink.append(extra)
                yield sse_token(extra)
            return

        ctx = {"load_input_files": load_input_files, "sandbox_url": sandbox_url, "save_file": save_file,
               "result": result, "finish": finish, "step": step}
        responses = []
        for call in calls:
            box = {}
            if call.name == "run_python_code":
                async for ev in _handle_code_call(_code_call(dict(call.args or {})), st, ctx, box):
                    yield ev
            else:
                box["output"] = f"Unknown tool '{call.name}'."
            responses.append(types.Part.from_function_response(name=call.name, response={"output": box.get("output") or ""}))
        contents.append(types.Content(role="model", parts=call_parts))
        contents.append(types.Content(role="user", parts=responses))

    yield sse(ERROR, {"message": "⚠️ Stopped after too many steps without finishing."})


def clean_provider_error(provider: str, exc: Exception) -> str:
    """Format upstream provider exceptions into friendly, actionable messages."""
    msg = str(exc)
    low = msg.lower()

    if provider == PROVIDER_OPENAI:
        if "deployment" in low and ("not found" in low or "404" in msg):
            return f"Azure OpenAI deployment not found. Please verify AZURE_OPENAI_DEPLOYMENT in .env: {msg}"
        if "credits remaining" in low or "billing" in low:
            return "OpenAI account has no credits remaining. Please add balance at platform.openai.com/settings/organization/billing."
        if "rate_limit" in low or "429" in msg or "quota" in low:
            return "AI model rate limit or quota exceeded. Please wait a moment or check your account quota."
        if "invalid_api_key" in low or "authentication" in low or "401" in msg:
            return "Invalid API Key. Please verify your Azure / OpenAI API key in .env."

    if provider == PROVIDER_GEMINI:
        if gemini_uses_openai():
            if "rate_limit" in low or "429" in msg or "quota" in low:
                return "AI model rate limit or quota exceeded. Please wait a moment and try again."
            if "invalid_api_key" in low or "authentication" in low or "401" in msg:
                return "Invalid API Key. Please verify your Azure / OpenAI API key in .env."
            return msg
        if "resource_exhausted" in low or "429" in msg or "quota" in low:
            return "Gemini API quota exceeded. Please check your quota at aistudio.google.com or provide an active Gemini API key in .env."
        if "not_found" in low or "404" in msg:
            return f"Gemini model not found. Check GEMINI_MODEL in settings or .env: {msg}"
        if "permission" in low or "forbidden" in low or "403" in msg:
            return "Gemini API access forbidden. Ensure your API key is active in Google AI Studio."

    if provider == PROVIDER_CLAUDE:
        if "credit balance" in low or "quota" in low or "429" in msg:
            return "Anthropic account has insufficient credits. Please top up your balance at console.anthropic.com/settings/plans."
        if "authentication" in low or "401" in msg:
            return "Invalid Anthropic API Key. Please verify ANTHROPIC_API_KEY in .env."
        if "workspace" in low and ("not found" in low or "404" in msg):
            ws = getattr(settings, 'ANTHROPIC_WORKSPACE_ID', '')
            return f"Anthropic Workspace not found ('{ws}'). Workspaces must belong to the same Organization as your API key ({msg})."
        if "anthropic-workspace-id" in low or "workspace" in low:
            return f"Anthropic workspace error: {msg}. Please verify ANTHROPIC_WORKSPACE_ID in .env or use a workspace-scoped key."
        if "model" in low and ("not found" in low or "404" in msg):
            return f"Claude model not found: {msg}. Please check CLAUDE_MODEL in settings or .env."

    return msg

