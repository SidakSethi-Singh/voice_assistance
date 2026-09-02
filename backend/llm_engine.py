import os
import json
import logging
import asyncio
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional, Callable
from backend.config import settings
from backend.tools.weather_tool import get_weather
from backend.tools.reminder_tool import manage_reminders
from backend.tools.rag_tool import query_knowledge_base

logger = logging.getLogger("voice_assistant.llm")

# Tool Declarations for Gemini Function Calling
TOOL_DECLARATIONS = [
    {
        "name": "get_weather",
        "description": "Fetch live current weather and forecasts for any city or location in the world.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city or location name (e.g. London, San Francisco, Tokyo, New York)."
                },
                "days_forecast": {
                    "type": "integer",
                    "description": "Number of days of forecast (1 for today only, up to 5 days)."
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "manage_reminders",
        "description": "Create, list, complete, or delete personal reminders and tasks in the persistent database.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "complete", "delete"],
                    "description": "The action to perform: 'create', 'list', 'complete', or 'delete'."
                },
                "title": {
                    "type": "string",
                    "description": "Title/description of the reminder (required for 'create')."
                },
                "due_time": {
                    "type": "string",
                    "description": "Due time or date description (e.g. '5:00 PM', 'tomorrow at noon')."
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priority level of the reminder."
                },
                "reminder_id": {
                    "type": "integer",
                    "description": "ID of the reminder to complete or delete."
                },
                "status_filter": {
                    "type": "string",
                    "enum": ["pending", "completed", "all"],
                    "description": "Filter status when listing reminders."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "query_knowledge_base",
        "description": "Search the local knowledge repository for documents regarding smart home devices, office facilities, Wi-Fi credentials, and assistant features.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or concept to look up in the local knowledge base."
                }
            },
            "required": ["query"]
        }
    }
]

SYSTEM_PROMPT = """You are Aether, a super-fast real-time voice assistant.
- Your answers are spoken out loud: keep them natural, punchy, and concise (1-2 short sentences max).
- Never use markdown lists, bullet points, asterisks, or tables.
- When you execute a tool, directly summarize the essential answer conversationally.
- Always use the tools (get_weather, manage_reminders, query_knowledge_base) whenever appropriate.
"""

class GeminiLLMEngine:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self._api_key = api_key
        self._model_name = model_name
        self.history: List[Dict[str, Any]] = []

    @property
    def api_key(self) -> str:
        return self._api_key or settings.GEMINI_API_KEY

    @api_key.setter
    def api_key(self, val: str):
        self._api_key = val

    @property
    def model_name(self) -> str:
        return self._model_name or settings.GEMINI_MODEL or "gemini-3.1-flash-lite"

    @model_name.setter
    def model_name(self, val: str):
        self._model_name = val

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch tool calls to corresponding python async functions."""
        logger.info(f"Executing tool '{tool_name}' with args: {arguments}")
        try:
            if tool_name == "get_weather":
                return await get_weather(
                    location=arguments.get("location", ""),
                    days_forecast=arguments.get("days_forecast", 1)
                )
            elif tool_name == "manage_reminders":
                return await manage_reminders(
                    action=arguments.get("action", "list"),
                    title=arguments.get("title"),
                    due_time=arguments.get("due_time"),
                    priority=arguments.get("priority", "medium"),
                    reminder_id=arguments.get("reminder_id"),
                    status_filter=arguments.get("status_filter")
                )
            elif tool_name == "query_knowledge_base":
                return await query_knowledge_base(
                    query=arguments.get("query", "")
                )
            else:
                return {"error": f"Unknown tool '{tool_name}'"}
        except Exception as e:
            logger.error(f"Error in tool execution {tool_name}: {e}")
            return {"error": str(e)}

    async def stream_chat(
        self,
        user_message: str,
        cancel_event: Optional[asyncio.Event] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], None]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream conversational responses from Gemini with multi-model fallback and structured tool execution.
        """
        if not self.api_key:
            yield "Gemini API key is not configured. Please add GEMINI_API_KEY to your .env file."
            return

        self.history.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })

        if len(self.history) > 12:
            self.history = self.history[-12:]

        payload = {
            "contents": self.history,
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "tools": [
                {"function_declarations": TOOL_DECLARATIONS}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 120
            }
        }

        candidate_models = [
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            "gemini-flash-lite-latest",
            "gemini-flash-latest"
        ]
        if self.model_name in candidate_models:
            candidate_models.remove(self.model_name)
        candidate_models.insert(0, self.model_name)

        full_assistant_response = ""
        captured_function_parts = []
        stream_successful = False
        winning_model = self.model_name

        try:
            for model_to_use in candidate_models:
                if stream_successful:
                    break

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_to_use}:streamGenerateContent?key={self.api_key}&alt=sse"
                captured_function_parts = []
                full_assistant_response = ""

                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        async with client.stream("POST", url, json=payload) as response:
                            if response.status_code != 200:
                                logger.warning(f"Model {model_to_use} status {response.status_code}. Trying next model...")
                                continue

                            async for line in response.aiter_lines():
                                if cancel_event and cancel_event.is_set():
                                    return

                                if not line or not line.startswith("data: "):
                                    continue

                                data_str = line[6:].strip()
                                if not data_str:
                                    continue

                                try:
                                    chunk = json.loads(data_str)
                                    candidates = chunk.get("candidates", [])
                                    if not candidates:
                                        continue

                                    content = candidates[0].get("content", {})
                                    parts = content.get("parts", [])

                                    for part in parts:
                                        if "text" in part:
                                            text_token = part["text"]
                                            full_assistant_response += text_token
                                            yield text_token

                                        if "functionCall" in part:
                                            captured_function_parts.append(part)

                                    stream_successful = True
                                    winning_model = model_to_use
                                except Exception:
                                    pass

                    if stream_successful:
                        break

                except Exception as e:
                    logger.warning(f"Error streaming from {model_to_use}: {e}")
                    continue

            # If tool calls were requested, execute them and make follow-up call
            if captured_function_parts:
                for fn_part in captured_function_parts:
                    if cancel_event and cancel_event.is_set():
                        return

                    fn_call = fn_part["functionCall"]
                    fn_name = fn_call.get("name")
                    fn_args = fn_call.get("args", {})

                    tool_result = await self.execute_tool(fn_name, fn_args)
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args, tool_result)

                    # Append original model part with thoughtSignature preserved
                    self.history.append({
                        "role": "model",
                        "parts": [fn_part]
                    })
                    # Append function response
                    self.history.append({
                        "role": "function",
                        "parts": [{
                            "functionResponse": {
                                "name": fn_name,
                                "response": tool_result
                            }
                        }]
                    })

                # Stream final synthesized response with tool context
                followup_payload = {
                    "contents": self.history,
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 120}
                }

                followup_url = f"https://generativelanguage.googleapis.com/v1beta/models/{winning_model}:streamGenerateContent?key={self.api_key}&alt=sse"

                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        async with client.stream("POST", followup_url, json=followup_payload) as response:
                            async for line in response.aiter_lines():
                                if cancel_event and cancel_event.is_set():
                                    return
                                if not line or not line.startswith("data: "):
                                    continue
                                data_str = line[6:].strip()
                                if not data_str:
                                    continue
                                try:
                                    chunk = json.loads(data_str)
                                    candidates = chunk.get("candidates", [])
                                    if not candidates:
                                        continue
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    for part in parts:
                                        if "text" in part:
                                            t = part["text"]
                                            full_assistant_response += t
                                            yield t
                                except Exception:
                                    pass
                except Exception as e:
                    logger.error(f"Followup error on {winning_model}: {e}")

            if full_assistant_response:
                self.history.append({
                    "role": "model",
                    "parts": [{"text": full_assistant_response}]
                })

        except asyncio.CancelledError:
            logger.info("LLM stream task was cancelled.")
        except Exception as e:
            logger.error(f"Error in Gemini chat stream: {e}")
            yield f"Error generating response: {str(e)}"
