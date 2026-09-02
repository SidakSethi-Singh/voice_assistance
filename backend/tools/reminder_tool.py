import sqlite3
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from backend.config import settings

DB_PATH = settings.DATA_DIR / "reminders.db"

def init_db():
    """Ensure reminders SQLite database exists with proper schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_time TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Initialize immediately on import
init_db()

async def manage_reminders(
    action: str,
    title: Optional[str] = None,
    due_time: Optional[str] = None,
    priority: str = "medium",
    reminder_id: Optional[int] = None,
    status_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manage personal reminders and tasks in the persistent database.
    
    Args:
        action: One of 'create', 'list', 'complete', or 'delete'.
        title: Title/content of the reminder (required for 'create').
        due_time: Time or date for the reminder (e.g. '5:00 PM', 'tomorrow morning', '2026-09-03 14:00').
        priority: 'low', 'medium', or 'high' (default 'medium').
        reminder_id: ID of the reminder (required for 'complete' and 'delete').
        status_filter: Filter for 'list' action ('pending', 'completed', or 'all'). Default 'pending'.
    """
    action = action.lower().strip()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if action == "create":
            if not title:
                return {"error": "A reminder title is required to create a reminder."}
            
            created_at = datetime.datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO reminders (title, due_time, priority, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (title, due_time or "not specified", priority.lower(), created_at)
            )
            conn.commit()
            new_id = cursor.lastrowid
            return {
                "status": "success",
                "message": f"Reminder created successfully with ID {new_id}",
                "reminder": {
                    "id": new_id,
                    "title": title,
                    "due_time": due_time or "not specified",
                    "priority": priority.lower(),
                    "status": "pending"
                }
            }

        elif action == "list":
            query = "SELECT id, title, due_time, priority, status, created_at FROM reminders"
            params: List[Any] = []
            if status_filter and status_filter.lower() != "all":
                query += " WHERE status = ?"
                params.append(status_filter.lower())
            else:
                # Default to listing pending first
                query += " WHERE status = 'pending'"

            query += " ORDER BY id DESC LIMIT 10"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            reminders = [dict(row) for row in rows]
            return {
                "status": "success",
                "count": len(reminders),
                "reminders": reminders
            }

        elif action == "complete":
            if not reminder_id:
                return {"error": "reminder_id is required to complete a reminder."}
            cursor.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return {"status": "success", "message": f"Reminder {reminder_id} marked as completed."}
            return {"error": f"No reminder found with ID {reminder_id}."}

        elif action == "delete":
            if not reminder_id:
                return {"error": "reminder_id is required to delete a reminder."}
            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return {"status": "success", "message": f"Reminder {reminder_id} deleted successfully."}
            return {"error": f"No reminder found with ID {reminder_id}."}

        else:
            return {"error": f"Unknown action '{action}'. Supported actions: 'create', 'list', 'complete', 'delete'."}

    except Exception as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        conn.close()
