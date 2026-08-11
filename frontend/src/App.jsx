import { useEffect, useRef, useState } from 'react'

const BACKEND = 'http://127.0.0.1:8000'
const API_BASE = import.meta.env.DEV ? '' : BACKEND
const WS_BASE = import.meta.env.DEV
  ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  : 'ws://127.0.0.1:8000'
const TOKEN_KEY = 'wyre_access_token'

const MSG_CHAT = 1
const MSG_ERROR = 2

function packMessage(msgType, payload) {
  const payloadBytes = new TextEncoder().encode(JSON.stringify(payload))
  const buffer = new ArrayBuffer(5 + payloadBytes.length)
  const view = new DataView(buffer)
  view.setUint8(0, msgType)
  view.setUint32(1, payloadBytes.length, false)
  new Uint8Array(buffer, 5).set(payloadBytes)
  return buffer
}

function unpackMessage(data) {
  const view = new DataView(data)
  const msgType = view.getUint8(0)
  const payloadLen = view.getUint32(1, false)
  const payloadBytes = new Uint8Array(data, 5, payloadLen)
  const payload = JSON.parse(new TextDecoder().decode(payloadBytes))
  return { msgType, payload }
}

function decodeJwtPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64))
  } catch {
    return null
  }
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [tokenInput, setTokenInput] = useState('')

  const [userInfo, setUserInfo] = useState(null)
  const [userError, setUserError] = useState('')

  const [otherUserId, setOtherUserId] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [convError, setConvError] = useState('')

  const [wsStatus, setWsStatus] = useState('Disconnected')
  const [recipientId, setRecipientId] = useState('')
  const [messageContent, setMessageContent] = useState('')
  const [wsMessages, setWsMessages] = useState([])

  const wsRef = useRef(null)

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  function saveToken() {
    const trimmed = tokenInput.trim()
    setToken(trimmed)
    localStorage.setItem(TOKEN_KEY, trimmed)
    setTokenInput('')
  }

  function logout() {
    setToken('')
    localStorage.removeItem(TOKEN_KEY)
    setUserInfo(null)
    wsRef.current?.close()
    wsRef.current = null
    setWsStatus('Disconnected')
  }

  async function fetchMe() {
    setUserError('')
    setUserInfo(null)
    try {
      const res = await fetch(`${API_BASE}/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || res.statusText)
      }
      const data = await res.json()
      const jwtPayload = decodeJwtPayload(token)
      setUserInfo({
        email: data.email,
        name: data.name,
        user_id: jwtPayload?.user_id ?? '(unknown)',
      })
    } catch (e) {
      setUserError(e.message)
    }
  }

  async function startConversation() {
    setConvError('')
    setConversationId(null)
    try {
      const res = await fetch(`${API_BASE}/conversations/start`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ other_user_id: Number(otherUserId) }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || res.statusText)
      }
      const data = await res.json()
      setConversationId(data.conversation_id)
    } catch (e) {
      setConvError(e.message)
    }
  }

  function connectWs() {
    if (!token) return
    wsRef.current?.close()
    setWsStatus('Connecting...')
    setWsMessages([])

    const ws = new WebSocket(`${WS_BASE}/ws?token=${encodeURIComponent(token)}`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => setWsStatus('Connected')
    ws.onclose = () => {
      setWsStatus('Disconnected')
      if (wsRef.current === ws) wsRef.current = null
    }
    ws.onerror = () => setWsStatus('Error')
    ws.onmessage = (event) => {
      try {
        const { msgType, payload } = unpackMessage(event.data)
        const label =
          msgType === MSG_CHAT ? 'CHAT' : msgType === MSG_ERROR ? 'ERROR' : `type=${msgType}`
        setWsMessages((prev) => [...prev, { label, payload }])
      } catch (e) {
        setWsMessages((prev) => [...prev, { label: 'PARSE_ERROR', payload: { error: e.message } }])
      }
    }
  }

  function sendMessage() {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const frame = packMessage(MSG_CHAT, {
      to: String(recipientId),
      content: messageContent,
    })
    wsRef.current.send(frame)
  }

  const tokenPreview = token ? `${token.slice(0, 30)}...` : '(none)'

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '1rem', maxWidth: 640 }}>
      <h1>Wyre Test Frontend</h1>

      <section style={{ marginBottom: '2rem' }}>
        <h2>Login</h2>
        <p>
          <button type="button" onClick={() => { window.location.href = `${BACKEND}/auth/login` }}>
            Sign in with Google
          </button>
        </p>
        <p>
          <input
            type="text"
            placeholder="Paste access_token here"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            style={{ width: '100%' }}
          />
        </p>
        <p>
          <button type="button" onClick={saveToken}>Save Token</button>
        </p>
        <p>Token: {tokenPreview}</p>
        <p>
          <button type="button" onClick={logout}>Logout</button>
        </p>
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2>Current User</h2>
        <p>
          <button type="button" onClick={fetchMe} disabled={!token}>
            Fetch My Info
          </button>
        </p>
        {userError && <p style={{ color: 'red' }}>{userError}</p>}
        {userInfo && (
          <ul>
            <li>Email: {userInfo.email}</li>
            <li>Name: {userInfo.name ?? '(none)'}</li>
            <li>User ID: {userInfo.user_id}</li>
          </ul>
        )}
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2>Start Conversation</h2>
        <p>
          <label>
            Other user id:{' '}
            <input
              type="number"
              value={otherUserId}
              onChange={(e) => setOtherUserId(e.target.value)}
            />
          </label>
        </p>
        <p>
          <button type="button" onClick={startConversation} disabled={!token || !otherUserId}>
            Start Conversation
          </button>
        </p>
        {convError && <p style={{ color: 'red' }}>{convError}</p>}
        {conversationId != null && <p>conversation_id: {conversationId}</p>}
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2>WebSocket Test</h2>
        <p>
          Status: <strong>{wsStatus}</strong>
        </p>
        <p>
          <button type="button" onClick={connectWs} disabled={!token}>
            Connect
          </button>
        </p>
        <p>
          <label>
            Recipient user id:{' '}
            <input
              type="text"
              value={recipientId}
              onChange={(e) => setRecipientId(e.target.value)}
            />
          </label>
        </p>
        <p>
          <label>
            Message content:{' '}
            <input
              type="text"
              value={messageContent}
              onChange={(e) => setMessageContent(e.target.value)}
              style={{ width: '100%' }}
            />
          </label>
        </p>
        <p>
          <button
            type="button"
            onClick={sendMessage}
            disabled={wsStatus !== 'Connected' || !recipientId || !messageContent}
          >
            Send
          </button>
        </p>
        {wsMessages.length > 0 && (
          <div>
            <h3>Received messages</h3>
            <ul>
              {wsMessages.map((msg, i) => (
                <li key={i}>
                  [{msg.label}] {JSON.stringify(msg.payload)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  )
}

export default App
