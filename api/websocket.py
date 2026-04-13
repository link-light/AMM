"""
WebSocket endpoint for real-time events

Events:
- new_signal: New opportunity discovered
- task_update: Task status changed
- human_task_created: New human intervention needed
- cost_alert: Budget threshold reached
- budget_warning: Budget level changed
- system_alert: System notifications
"""

import json
import logging
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from core.config import settings

logger = logging.getLogger(__name__)

# Connected clients
connected_clients: Set[WebSocket] = set()


class ConnectionManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        await websocket.send_json(message)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time events
    
    Connection URL: /ws/events
    
    Events format:
    {
        "type": "new_signal|task_update|human_task_created|cost_alert|budget_warning|system_alert",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {...}
    }
    """
    await manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle client messages (e.g., subscription requests)
                if message.get("action") == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                        websocket
                    )
                    
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "message": "Invalid JSON"},
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Event broadcasting functions
async def broadcast_new_signal(signal_data: dict):
    """Broadcast new signal event"""
    await manager.broadcast({
        "type": "new_signal",
        "timestamp": datetime.utcnow().isoformat(),
        "data": signal_data,
    })


async def broadcast_task_update(task_id: str, status: str, data: dict = None):
    """Broadcast task update event"""
    await manager.broadcast({
        "type": "task_update",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "task_id": task_id,
            "status": status,
            **(data or {}),
        },
    })


async def broadcast_human_task_created(task_data: dict):
    """Broadcast human task creation"""
    await manager.broadcast({
        "type": "human_task_created",
        "timestamp": datetime.utcnow().isoformat(),
        "data": task_data,
    })


async def broadcast_cost_alert(level: str, current: float, limit: float):
    """Broadcast cost alert"""
    await manager.broadcast({
        "type": "cost_alert",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "level": level,
            "current": current,
            "limit": limit,
            "percentage": round(current / limit * 100, 2),
        },
    })


async def broadcast_budget_warning(level: str, details: dict):
    """Broadcast budget warning"""
    await manager.broadcast({
        "type": "budget_warning",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "level": level,
            "details": details,
        },
    })


async def broadcast_system_alert(message: str, severity: str = "info"):
    """Broadcast system alert"""
    await manager.broadcast({
        "type": "system_alert",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "message": message,
            "severity": severity,
        },
    })


from datetime import datetime
