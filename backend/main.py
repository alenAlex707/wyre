import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from auth import GOOGLE_REDIRECT_URI, create_jwt, oauth, verify_jwt
from crypto_utils import generate_aes_key, generate_rsa_keypair, rsa_encrypt
from database import Base, engine, get_db
from models import Conversation, User
from protocol import MSG_CHAT, MSG_ERROR, pack_message, unpack_message

load_dotenv()

SESSION_SECRET = os.getenv("SESSION_SECRET")

app = FastAPI(title="wyre")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
active_connections: dict[str, WebSocket] = {}

Base.metadata.create_all(bind=engine)


class StartConversationRequest(BaseModel):
    other_user_id: int


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
        private_key_pem, public_key_pem = generate_rsa_keypair()
        user = User(
            email=email,
            name=name,
            google_id=google_id,
            public_key=public_key_pem,
            private_key=private_key_pem,
        )
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


@app.post("/conversations/start")
def start_conversation(
    body: StartConversationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.removeprefix("Bearer ")
    user_id = verify_jwt(token)

    current_user = db.query(User).filter(User.id == user_id).first()
    if current_user is None:
        raise HTTPException(status_code=401, detail="User not found")

    other_user = db.query(User).filter(User.id == body.other_user_id).first()
    if other_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        db.query(Conversation)
        .filter(
            or_(
                and_(
                    Conversation.user_a_id == user_id,
                    Conversation.user_b_id == body.other_user_id,
                ),
                and_(
                    Conversation.user_a_id == body.other_user_id,
                    Conversation.user_b_id == user_id,
                ),
            )
        )
        .first()
    )
    if existing is not None:
        return {"conversation_id": existing.id}

    aes_key = generate_aes_key()

    # The same shared AES key is encrypted twice — once per participant's public
    # key — because only that user's matching private key can unwrap their copy.
    encrypted_key_for_a = rsa_encrypt(current_user.public_key, aes_key)
    encrypted_key_for_b = rsa_encrypt(other_user.public_key, aes_key)

    conversation = Conversation(
        user_a_id=user_id,
        user_b_id=body.other_user_id,
        encrypted_key_for_a=encrypted_key_for_a,
        encrypted_key_for_b=encrypted_key_for_b,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {"conversation_id": conversation.id}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(code=1008)
        return

    try:
        user_id = str(verify_jwt(token))
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"{user_id} connected")
    try:
        while True:
            raw = await websocket.receive_bytes()
            try:
                _, data = unpack_message(raw)
                recipient_id = data["to"]
                content = data["content"]
            except (ValueError, KeyError, TypeError):
                await websocket.send_bytes(
                    pack_message(MSG_ERROR, {"error": "invalid message format"})
                )
                continue

            recipient = active_connections.get(recipient_id)
            if recipient is not None:
                await recipient.send_bytes(
                    pack_message(MSG_CHAT, {"from": user_id, "content": content})
                )
            else:
                await websocket.send_bytes(
                    pack_message(MSG_ERROR, {"error": f"{recipient_id} is not online"})
                )
    except WebSocketDisconnect:
        del active_connections[user_id]
        print(f"{user_id} disconnected")
