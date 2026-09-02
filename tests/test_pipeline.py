import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.main import app
from backend.tools.weather_tool import get_weather
from backend.tools.reminder_tool import manage_reminders
from backend.tools.rag_tool import query_knowledge_base
from backend.llm_engine import GeminiLLMEngine

client = TestClient(app)

def test_health_endpoint():
    """Verify health endpoint returns status online and knowledge chunks."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "gemini_model" in data
    assert data["knowledge_chunks"] > 0

@pytest.mark.asyncio
async def test_llm_tool_dispatch():
    """Test that GeminiLLMEngine can execute tools via execute_tool dispatch."""
    llm = GeminiLLMEngine(api_key="test_dummy_key")

    # 1. Weather tool dispatch
    weather_res = await llm.execute_tool("get_weather", {"location": "Paris", "days_forecast": 1})
    assert "temperature_celsius" in weather_res
    assert "Paris" in weather_res["location"]

    # 2. Reminder tool dispatch
    reminder_res = await llm.execute_tool("manage_reminders", {
        "action": "create",
        "title": "Pipeline Integration Test Task",
        "due_time": "5 PM"
    })
    assert reminder_res["status"] == "success"
    rem_id = reminder_res["reminder"]["id"]

    # Delete the created reminder to keep clean
    del_res = await llm.execute_tool("manage_reminders", {"action": "delete", "reminder_id": rem_id})
    assert del_res["status"] == "success"

    # 3. RAG tool dispatch
    rag_res = await llm.execute_tool("query_knowledge_base", {"query": "office wifi credentials"})
    assert rag_res["status"] == "success"
    assert len(rag_res["results"]) > 0

@pytest.mark.asyncio
async def test_barge_in_cancellation_logic():
    """Verify that setting cancel_event stops streaming generators immediately."""
    cancel_event = asyncio.Event()

    async def dummy_token_stream():
        for i in range(100):
            if cancel_event.is_set():
                break
            yield f"token_{i} "
            await asyncio.sleep(0.01)

    collected = []
    
    async def consumer():
        async for tok in dummy_token_stream():
            collected.append(tok)
            if len(collected) == 3:
                # Trigger barge-in
                cancel_event.set()

    await consumer()
    # Should stop after cancellation without completing 100 items
    assert len(collected) == 3
    assert cancel_event.is_set()

def test_wake_word_detection():
    """Verify wake-word pattern matching and phrase extraction."""
    import re
    wake_regex = re.compile(r'\b(hey aether|aether|hey either|wake up)\b', re.IGNORECASE)

    # Trigger with full phrase
    match1 = wake_regex.search("Hey Aether what is the weather in London")
    assert match1 is not None
    cleaned = wake_regex.sub("", "Hey Aether what is the weather in London").strip()
    assert cleaned == "what is the weather in London"

    # Trigger standalone
    match2 = wake_regex.search("aether")
    assert match2 is not None
