"""
LLM-assisted ticket triage module for ServiceDesk-AI.

Provides canonical definitions, JSON schema, prompt builders, output validation,
and Ollama API communication for zero-shot and RAG-augmented IT ticket triage.
Standard library only (no third-party dependencies).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Sequence
import urllib.error
import urllib.request

logger = logging.getLogger("helpdesk_api")

CATEGORIES = ["network", "hardware", "software", "access", "email", "other"]
PRIORITIES = ["low", "medium", "high", "urgent"]

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.1:8b"

OLLAMA_FORMAT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": CATEGORIES,
        },
        "priority": {
            "type": "string",
            "enum": PRIORITIES,
        },
    },
    "required": ["category", "priority"],
}

SYSTEM_PROMPT = """You are an expert IT service desk triage assistant.
Your task is to classify an incoming IT support ticket into exactly one category and one operational priority tier based on the following canonical definitions:

CATEGORIES:
- network: Wi-Fi connectivity, wired Ethernet, VPN access/routing, DNS resolution, corporate switches/routers, firewall blocks, remote connectivity, and ISP/site-wide connectivity issues.
- hardware: Physical computing devices, laptop/desktop hardware failures, external monitors/peripherals, docks/cables, physical servers/disks, and procurement requests for new devices.
- software: Application and operating system installations, application crashes, license activations, error popups, updates, browser bugs, and software configuration issues.
- access: Password resets, locked accounts, MFA token issues, SSO authentication failures, file/folder permissions, role-based access requests, joiner/mover/leaver account provisioning.
- email: Mailbox quotas, Outlook/webmail client issues, calendar synchronization and scheduling, shared mailboxes, distribution list management, spam/phishing reports, and email delivery failures.
- other: Inquiries fitting none of the above categories, general how-to questions, user training requests, audiovisual/conferencing assistance, facilities/furniture requests, or vague general inquiries.

PRIORITIES:
- urgent: Site-wide or multi-user outage affecting business operations, mission-critical production service down, active security incident, or imminent data loss.
- high: Individual user or small team completely blocked with no viable workaround, or critical deadline/executive presentation at immediate risk.
- medium: Degraded performance, single-user malfunction with a temporary workaround, or non-blocking functional inconvenience.
- low: Standard service request, scheduled future change, cosmetic flaw, how-to inquiry, or informational question.

You must respond ONLY with a JSON object containing "category" and "priority"."""


def extract_ticket_text(ticket: Any) -> str:
    """Extract full problem text (title + description) from a ticket object, dict, or string."""
    if isinstance(ticket, str):
        return ticket.strip()
    if hasattr(ticket, "text"):
        return str(ticket.text).strip()
    if isinstance(ticket, dict):
        if "text" in ticket:
            return str(ticket["text"]).strip()
        title = str(ticket.get("title", "")).strip()
        description = str(ticket.get("description", "")).strip()
        if title and description:
            return f"{title}\n{description}"
        return title or description
    return str(ticket).strip()


def build_zero_shot_prompt(ticket: Any) -> str:
    """Build the user prompt for zero-shot LLM triage."""
    text = extract_ticket_text(ticket)
    return f"""Please triage the following support ticket:

TICKET:
{text}"""


def build_rag_prompt(
    ticket: Any,
    retrieved_examples: Sequence[Any],
) -> str:
    """
    Build the user prompt with in-context retrieved reference tickets.
    Matches the benchmark prompt structure exactly.
    """
    examples_str_list = []
    for idx, ex in enumerate(retrieved_examples, 1):
        ex_text = extract_ticket_text(ex)

        if hasattr(ex, "category"):
            ex_cat = ex.category
        elif isinstance(ex, dict):
            ex_cat = ex.get("category", "")
        else:
            ex_cat = ""
        if hasattr(ex_cat, "value"):
            ex_cat = ex_cat.value
        ex_cat = str(ex_cat).strip().lower()

        if hasattr(ex, "priority"):
            ex_prio = ex.priority
        elif isinstance(ex, dict):
            ex_prio = ex.get("priority", "")
        else:
            ex_prio = ""
        if hasattr(ex_prio, "value"):
            ex_prio = ex_prio.value
        ex_prio = str(ex_prio).strip().lower()

        examples_str_list.append(
            f"--- Reference Ticket #{idx} ---\n"
            f"{ex_text}\n"
            f"Category: {ex_cat}\n"
            f"Priority: {ex_prio}"
        )
    examples_block = "\n\n".join(examples_str_list)
    ticket_text = extract_ticket_text(ticket)

    return f"""Here are 5 similar resolved tickets from our historical knowledge base for reference:

{examples_block}

---
Please triage the following new support ticket:

TICKET:
{ticket_text}"""


def check_ollama_status(
    base_url: str = DEFAULT_OLLAMA_URL,
    model_name: str = DEFAULT_MODEL,
    timeout: float = 5.0,
) -> tuple[bool, str, str]:
    """
    Check if Ollama server is reachable and target model is installed.
    Returns (is_available, error_message, digest).
    """
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": "ServiceDesk-AI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return False, f"Could not reach Ollama at {tags_url}: {exc.reason}", ""
    except Exception as exc:
        return False, f"Failed connecting to Ollama at {tags_url}: {exc}", ""

    models = data.get("models", [])
    target_clean = model_name.strip()
    target_base = target_clean.split(":")[0]

    matched_digest = ""
    for m in models:
        m_name = m.get("name", "")
        m_model = m.get("model", "")
        if target_clean in (m_name, m_model):
            matched_digest = m.get("digest", "")
            return True, "", matched_digest
        if target_base == m_name.split(":")[0]:
            matched_digest = m.get("digest", "")
            return True, "", matched_digest

    installed = [m.get("name", "") for m in models]
    return (
        False,
        f"Model '{model_name}' is not installed in Ollama. Installed models: {installed}",
        "",
    )


def parse_and_validate_llm_response(
    content: str,
) -> tuple[str | None, str | None, str | None]:
    """
    Parse and validate LLM JSON output.
    Returns:
        (category, priority, error_reason)
        If valid: (category, priority, None)
        If invalid: (None, None, error_reason)
    """
    if not content or not content.strip():
        return None, None, "empty response from LLM"

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, None, f"invalid JSON: {exc.msg}"

    if not isinstance(parsed, dict):
        return None, None, "response JSON is not an object"

    cat = str(parsed.get("category", "")).strip().lower()
    prio = str(parsed.get("priority", "")).strip().lower()

    if cat not in CATEGORIES and prio not in PRIORITIES:
        return None, None, f"invalid category '{cat}' and priority '{prio}'"
    if cat not in CATEGORIES:
        return None, None, f"invalid category '{cat}'"
    if prio not in PRIORITIES:
        return None, None, f"invalid priority '{prio}'"

    return cat, prio, None


def call_ollama_chat(
    model_name: str,
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout: float = 30.0,
    max_retries: int = 1,
) -> tuple[str | None, str | None, float, bool]:
    """
    Call Ollama POST /api/chat with stream=false, temperature=0, seed=42, and JSON schema format.
    Retries once on JSON decode error or invalid labels.
    Returns (pred_category, pred_priority, latency_ms, is_invalid).
    Maintains exact backward compatibility with benchmark_triage.py.
    """
    chat_url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model_name,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42,
        },
        "format": OLLAMA_FORMAT_SCHEMA,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req_data = json.dumps(payload).encode("utf-8")
    total_latency_ms = 0.0

    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                chat_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "ServiceDesk-AI/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                resp_json = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += latency_ms
            if attempt < max_retries:
                continue
            return None, None, total_latency_ms, True

        latency_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += latency_ms

        content = resp_json.get("message", {}).get("content", "")
        cat, prio, err = parse_and_validate_llm_response(content)
        if cat is not None and prio is not None:
            return cat, prio, total_latency_ms, False

        if attempt >= max_retries:
            break

    return None, None, total_latency_ms, True


def triage_with_llm(
    ticket_text: str,
    retrieved_examples: Sequence[Any],
    model_name: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout: float = 30.0,
    system_prompt: str = SYSTEM_PROMPT,
    max_retries: int = 1,
) -> tuple[str | None, str | None, float, str | None]:
    """
    Execute LLM-assisted triage request against Ollama.
    Returns:
        (category, priority, latency_ms, fallback_reason)
        On success: (category, priority, latency_ms, None)
        On failure: (None, None, latency_ms, short_fallback_reason)
    """
    # 1. Health/model check (fast timeout)
    is_ok, err_msg, _ = check_ollama_status(base_url=base_url, model_name=model_name, timeout=min(5.0, timeout))
    if not is_ok:
        logger.warning("Ollama pre-check failed: %s", err_msg)
        return None, None, 0.0, err_msg

    # 2. Build prompt
    if retrieved_examples:
        user_prompt = build_rag_prompt(ticket_text, retrieved_examples)
    else:
        user_prompt = build_zero_shot_prompt(ticket_text)

    # 3. Call Ollama chat
    chat_url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model_name,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42,
        },
        "format": OLLAMA_FORMAT_SCHEMA,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req_data = json.dumps(payload).encode("utf-8")
    total_latency_ms = 0.0

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                chat_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "ServiceDesk-AI/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                resp_json = json.loads(raw_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += latency_ms
            last_error = f"Ollama HTTP error {exc.code}: {exc.reason}"
            if attempt < max_retries:
                continue
            return None, None, total_latency_ms, last_error
        except urllib.error.URLError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += latency_ms
            last_error = f"Ollama connection error: {exc.reason}"
            if attempt < max_retries:
                continue
            return None, None, total_latency_ms, last_error
        except (TimeoutError, OSError) as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += latency_ms
            last_error = f"Ollama request timed out after {timeout}s: {exc}"
            if attempt < max_retries:
                continue
            return None, None, total_latency_ms, last_error
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += latency_ms
            last_error = f"Ollama request failed: {exc}"
            if attempt < max_retries:
                continue
            return None, None, total_latency_ms, last_error

        latency_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += latency_ms

        content = resp_json.get("message", {}).get("content", "")
        cat, prio, parse_err = parse_and_validate_llm_response(content)
        if cat is not None and prio is not None:
            return cat, prio, total_latency_ms, None

        last_error = f"Invalid LLM output: {parse_err}"
        if attempt >= max_retries:
            break

    return None, None, total_latency_ms, last_error or "LLM triage failed"

