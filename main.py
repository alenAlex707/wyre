import json
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from auth import GOOGLE_REDIRECT_URI, create_jwt, oauth, verify_jwt
from database import Base, engine, get_db
from models import User

load_dotenv()

SESSION_SECRET = os.getenv("SESSION_SECRET")

app = FastAPI(title="wyre")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
active_connections: dict[str, WebSocket] = {}

Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"status": "server running"}


@app.post("/test-db")
def create_test_user(db: Session = Depends(get_db)):
    user = User(email="[email protected]", name="Test User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email}


@app.get("/test-db")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "google_id": user.google_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        for user in users
    ]


@app.get("/auth/login")
async def login(request: Request):
    return await oauth.google.authorize_redirect(request, GOOGLE_REDIRECT_URI)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token["userinfo"]

    email = userinfo["email"]
    name = userinfo.get("name")
    google_id = userinfo["sub"]

    user = db.query(User).filter(User.google_id == google_id).first()
    if user is None:
        user = User(email=email, name=name, google_id=google_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_jwt(user.id)
    return {"access_token": jwt_token, "token_type": "bearer"}


@app.get("/me")
def get_me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.removeprefix("Bearer ")
    user_id = verify_jwt(token)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {"email": user.email, "name": user.name}


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
