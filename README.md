# 🎙️ AI Meeting Assistant

> A real-time meeting assistant that captures microphone/system audio, transcribes conversations locally, and uses Google Gemini to generate meeting summaries, action items, and follow-up questions.

![AI Meeting Assistant](assets/System_Architecture.png)

## ✨ What it does

AI Meeting Assistant helps turn a live conversation into structured meeting intelligence.

### Core features

- 🎤 **Live audio capture** — captures microphone audio and browser/system audio.
- 📝 **Real-time transcription** — transcribes audio locally with **faster-whisper**.
- 🧠 **AI meeting summary** — generates concise summaries, topics, and decisions.
- ✅ **Action-item extraction** — identifies tasks, assignees, priorities, and due dates when available.
- ❓ **Follow-up questions** — generates questions that help clarify next steps and open issues.
- 🔄 **Progressive insights** — updates meeting insights while a meeting is in progress.
- 📚 **Meeting history** — stores meetings and their transcripts/insights for later review.
- 🔌 **REST + WebSocket APIs** — WebSockets handle live audio/transcription while REST APIs manage meetings and insights.
- 🗄️ **PostgreSQL persistence** — stores meetings, transcripts, summaries, action items, follow-up questions, and topics.

---

## 📸 Screenshots

### 🏠 Dashboard

![Dashboard](assets/screenshots/dashboard.png)

### 🎙️ Live Meeting & Real-Time Transcript

![Live Meeting](assets/screenshots/live-meeting.png)

### 📚 Meeting History

![Meeting History](assets/screenshots/meeting-history.png)

### Meeting workspace

### System architecture

![System Architecture](assets/System_Architecture.png)

### Database architecture

![Database Architecture](assets/db_architecture.png)

---

## 🏗️ Architecture

```text
┌───────────────────────────────┐
│        React + TypeScript     │
│                               │
│  Meeting UI • History •       │
│  Audio Capture • Live Insights│
└───────────────┬───────────────┘
                │
          REST + WebSocket
                │
                ▼
┌───────────────────────────────┐
│          FastAPI              │
│                               │
│  Meeting APIs                 │
│  WebSocket audio pipeline     │
│  Audio processing             │
│  AI insight generation        │
└───────┬───────────────┬───────┘
        │               │
        ▼               ▼
┌──────────────┐  ┌────────────────┐
│ faster-whisper│  │ Google Gemini │
│ Local STT     │  │ AI Analysis   │
└──────────────┘  └────────────────┘
        │
        ▼
┌───────────────────────────────┐
│          PostgreSQL           │
│                               │
│ Meetings • Transcripts •      │
│ Summaries • Action Items •    │
│ Follow-up Questions • Topics  │
└───────────────────────────────┘
```

### Request flow

1. The React frontend creates a meeting through the FastAPI REST API.
2. `AudioRecorder` opens a WebSocket connection and streams audio.
3. The backend buffers and processes audio through `EnhancedAudioProcessor`.
4. `faster-whisper` performs local speech-to-text.
5. Final transcript segments are persisted in PostgreSQL.
6. The live-insights endpoint sends recent transcript context to Google Gemini.
7. Gemini returns structured JSON for summaries, action items, and follow-up questions.
8. The frontend renders the generated insights in the meeting workspace.
9. Meeting data remains available through the history/details APIs.

---

## 🛠️ Tech Stack

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Axios
- Lucide React

### Backend
- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- WebSockets

### Speech & AI
- faster-whisper for local speech-to-text
- Google Gemini API for meeting analysis
- Structured JSON AI responses

### Database
- PostgreSQL
- SQLAlchemy ORM

### Audio / Processing
- NumPy
- SciPy
- Web Audio API
- Browser `getUserMedia` / `getDisplayMedia`

### Testing & Tooling
- Pytest
- Git / GitHub

---

## 📁 Project Structure

```text
Meeting-Assistant/
├── backend/
│   ├── app/
│   │   ├── config/
│   │   ├── core/
│   │   │   ├── audio/
│   │   │   └── meeting_manager.py
│   │   ├── database/
│   │   ├── routers/
│   │   ├── services/
│   │   └── main.py
│   ├── alembic/
│   ├── scripts/
│   ├── tests/
│   ├── .env.example
│   ├── requirements.txt
│   └── alembic.ini
│
├── extension/
│   └── # optional browser-extension code
│
├── assets/
│   ├── System_Architecture.png
│   └── db_architecture.png
│
├── ui/
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── .gitignore
└── README.md
```

---

## 🚀 Run locally

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL
- A Google Gemini API key
- A browser with microphone and screen/system-audio capture support

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd Meeting-Assistant
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
copy .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

Then edit `.env` and add your real Gemini and PostgreSQL values.

Run database migrations:

```bash
alembic upgrade head
```

Start FastAPI:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Backend:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

### 3. Frontend setup

Open a second terminal:

```bash
cd ui
npm install
npm run dev
```

Frontend:

```text
http://localhost:5173
```

---

## 🔐 Environment variables

Never commit `.env` or API keys to GitHub.

Create `backend/.env` from `backend/.env.example`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
DATABASE_URL=postgresql+psycopg2://username:password@host:5432/database_name
```

> **Security:** Keep API keys and database credentials private. If a secret has ever been committed to a public repository, revoke/rotate it immediately.

---

## 📡 API overview

### REST

| Endpoint | Purpose |
|---|---|
| `POST /meetings/` | Create a meeting |
| `GET /meetings/` | List meetings |
| `GET /meetings/{meeting_id}/details` | Get meeting details |
| `PUT /meetings/{meeting_id}/end` | End a meeting |
| `DELETE /meetings/{meeting_id}` | Delete a meeting |
| `POST /meetings/{meeting_id}/live-insights` | Generate progressive AI insights |
| `POST /meetings/{meeting_id}/generate-summary` | Generate final meeting summary |
| `GET /health` | Health check |

### WebSocket

```text
/ws/{client_id}
```

Used for live audio streaming and real-time transcript events.

---

## 🧪 Testing

Backend tests are included under:

```text
backend/tests/
```

Run:

```bash
cd backend
pytest
```

For the frontend, build the production bundle with:

```bash
cd ui
npm run build
```

---

## 🔍 Engineering highlights

### Local transcription

Speech-to-text is handled with `faster-whisper`, keeping the transcription pipeline local instead of sending raw audio to a third-party speech API.

### Real-time communication

The application uses a WebSocket connection for streaming audio from the browser to FastAPI and returning transcript/status events.

### AI output normalization

Gemini responses are requested as JSON and parsed/normalized before being returned to the frontend. This keeps the UI response shape predictable even when individual insight fields are missing.

### Resilience

The AI service includes retry handling and rate limiting to reduce failures caused by temporary API errors or request bursts.

### Database design

Meeting data is separated into related tables for transcripts, summaries, action items, follow-up questions, and topics, with SQLAlchemy relationships and Alembic migrations.

---

## 🚧 Future improvements

These are intentionally **not part of the current version**:

- 🔐 User authentication and signup/login
- 👤 User-specific meeting ownership and permissions
- ☁️ Production cloud deployment
- 📅 Calendar integrations
- 🗣️ Advanced speaker identification
- 📤 Meeting export (PDF/Markdown)
- 🌍 Multilingual transcription and analysis
- 📱 Mobile experience

---

## 🎯 Project status

**Current version:** Functional local MVP

The core meeting workflow is implemented:

> **Record → Transcribe → Analyze → Review**

Authentication and production deployment are planned as subsequent improvements.

---

## 👨‍💻 Author

**Tushar Sharma**

B.Tech — Computer Science & Engineering Graduate

---

## ⭐ If you find this project useful

Feel free to star the repository and explore the implementation.
