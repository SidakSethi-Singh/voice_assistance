import pytest
import pytest_asyncio
from backend.tools.weather_tool import get_weather
from backend.tools.reminder_tool import manage_reminders
from backend.tools.rag_tool import query_knowledge_base

@pytest.mark.asyncio
async def test_weather_tool_live():
    # Test real weather API call
    result = await get_weather("London", days_forecast=2)
    assert "error" not in result, f"Weather tool returned error: {result.get('error')}"
    assert "temperature_celsius" in result
    assert "London" in result["location"]
    assert "forecast" in result
    assert len(result["forecast"]) >= 2

@pytest.mark.asyncio
async def test_reminder_tool_crud():
    # 1. Create reminder
    create_res = await manage_reminders(
        action="create",
        title="Test meeting with team",
        due_time="tomorrow at 3 PM",
        priority="high"
    )
    assert create_res["status"] == "success"
    rem_id = create_res["reminder"]["id"]
    assert rem_id is not None

    # 2. List reminders
    list_res = await manage_reminders(action="list", status_filter="pending")
    assert list_res["status"] == "success"
    assert any(r["id"] == rem_id for r in list_res["reminders"])

    # 3. Complete reminder
    comp_res = await manage_reminders(action="complete", reminder_id=rem_id)
    assert comp_res["status"] == "success"

    # 4. Delete reminder
    del_res = await manage_reminders(action="delete", reminder_id=rem_id)
    assert del_res["status"] == "success"

@pytest.mark.asyncio
async def test_rag_tool_retrieval():
    # Test querying smart home
    res1 = await query_knowledge_base("what is the wifi password")
    assert res1["status"] == "success"
    assert len(res1["results"]) > 0
    assert "HyperScale2026!" in res1["results"][0]["text"]

    # Test querying movie night scene
    res2 = await query_knowledge_base("movie night lights scene")
    assert res2["status"] == "success"
    assert len(res2["results"]) > 0
    assert "Movie Night Scene" in res2["results"][0]["text"]
