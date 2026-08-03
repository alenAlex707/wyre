import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="wyre")
active_connections: dict[str, WebSocket] = {}


@app.get("/")
def root():
    return {"status": "server running"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"{user_id} connected")
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                recipient_id = data["to"]
                content = data["content"]
            except (json.JSONDecodeError, KeyError, TypeError):
                await websocket.send_text(json.dumps({"error": "invalid message format"}))
                continue

            recipient = active_connections.get(recipient_id)
            if recipient is not None:
                await recipient.send_text(
                    json.dumps({"from": user_id, "content": content})
                )
            else:
                await websocket.send_text(
                    json.dumps({"error": f"{recipient_id} is not online"})
                )
    except WebSocketDisconnect:
        del active_connections[user_id]
        print(f"{user_id} disconnected")
