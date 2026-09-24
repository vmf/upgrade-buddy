"""Shared helpers for calling Claude with a forced structured-output tool.

This is the one place every pipeline stage funnels through to talk to the
model, so retries/validation/logging are handled consistently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from core.claude import Claude
from schema.risk_model import to_anthropic_tool

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def render_prompt(template: str, **kwargs) -> str:
    """Substitutes `{{key}}` placeholders. Non-string values are JSON-dumped
    so prompts can embed structured data without the template author having
    to serialize it themselves. Deliberately not str.format() - prompts
    contain literal JSON examples full of unrelated `{...}` braces.
    """

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in kwargs:
            raise KeyError(f"Missing prompt placeholder: {{{{{key}}}}}")
        value = kwargs[key]
        return value if isinstance(value, str) else json.dumps(value, indent=2, default=str)

    return _PLACEHOLDER_RE.sub(_sub, template)


def call_structured(
    claude: Claude,
    *,
    prompt: str,
    output_model: type[T],
    tool_name: str,
    tool_description: str,
    system: str | None = None,
    max_retries: int = 2,
    max_tokens: int = 8000,
) -> T:
    """Calls Claude with `tool_choice` forced to a schema-only tool built from
    `output_model`, parses+validates the tool call's input, and retries (by
    feeding the validation error back to the model) if it doesn't validate.
    Raises the last ValidationError if all retries are exhausted - a stage
    that can't get valid structured output should fail loudly, not silently
    emit something malformed.
    """
    tool_schema = to_anthropic_tool(output_model, tool_name, tool_description)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        response = claude.chat(
            messages=messages,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
            max_tokens=max_tokens,
        )
        if response.stop_reason == "max_tokens":
            # The tool call was truncated mid-JSON - its `input` may still
            # parse as *technically* schema-valid (e.g. an empty list),
            # which would silently pass validation below and look like a
            # legitimate "nothing found" result. Never accept a truncated
            # response; retry with more room instead.
            last_error = RuntimeError(
                f"Response hit max_tokens={max_tokens} before completing the tool call; retrying with more room."
            )
            claude.add_assistant_message(messages, response)
            claude.add_user_message(
                messages,
                [{"type": "text", "text": "Your previous response was cut off. Please answer again, more concisely."}],
            )
            max_tokens = min(max_tokens * 2, 64_000)
            continue
        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use is None:
            last_error = RuntimeError("Model response contained no tool_use block")
            claude.add_assistant_message(messages, response)
            claude.add_user_message(
                messages,
                [{"type": "text", "text": "You must respond using the tool call, with no other content."}],
            )
            continue
        try:
            return output_model.model_validate(tool_use.input)
        except ValidationError as exc:
            last_error = exc
            claude.add_assistant_message(messages, response)
            claude.add_user_message(
                messages,
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Your output failed schema validation:\n{exc}\nPlease call the tool again with corrected input.",
                        "is_error": True,
                    }
                ],
            )

    assert last_error is not None
    raise last_error
