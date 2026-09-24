from anthropic import Anthropic
from anthropic.types import Message


class Claude:
    def __init__(self, model: str):
        self.client = Anthropic()
        self.model = model

    def add_user_message(self, messages: list, message):
        user_message = {
            "role": "user",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(user_message)

    def add_assistant_message(self, messages: list, message):
        assistant_message = {
            "role": "assistant",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(assistant_message)

    def text_from_message(self, message: Message):
        return "\n".join(
            [block.text for block in message.content if block.type == "text"]
        )

    def chat(
        self,
        messages,
        system=None,
        stop_sequences=[],
        tools=None,
        tool_choice=None,
        thinking=False,
        thinking_budget=1024,
        max_tokens=8000,
    ) -> Message:
        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stop_sequences": stop_sequences,
        }

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if tool_choice:
            params["tool_choice"] = tool_choice

        if system:
            params["system"] = system

        message = self.client.messages.create(**params)
        return message
