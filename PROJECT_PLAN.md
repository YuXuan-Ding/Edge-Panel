# Panda Sidekick – Combined Project Plan

## Project Overview
A lightweight, always-on-top desktop companion that lives on the edge of your screen as an animated panda. It answers homework questions, explains concepts, and later grows into a personal assistant for email, calendar, and tasks — but **only after the foundations are solid**.

## Core Principles (from your feedback)
1. **Build in strict layers** — feature creep is the biggest risk.
2. **Polish the feeling** before adding functionality. A chat window with panda PNGs is worthless. The character must feel alive.
3. **AI is not the hard part** — desktop integration, state management, animation, and security are.
4. **LLMs suggest intent, code executes actions** — never let the AI directly call APIs.
5. **Use Claude for architecture and debugging, DeepSeek for boilerplate** — with human review on everything.

## Tech Stack (Final)
| Layer | Technology |
|-------|------------|
| Desktop shell | Electron + React + TypeScript |
| Styling | TailwindCSS |
| Animations | Rive (skeletal animation), Framer Motion for UI transitions |
| AI | Claude API (primary reasoning), DeepSeek (cheap background tasks) |
| AI abstraction | Custom `AIProvider` interface, prompt template manager |
| Backend in Electron | Node/Express, SQLite (local chat persistence, memory) |
| Integrations (later) | Google Calendar/Gmail APIs, Microsoft Graph |
| Packaging | Electron Builder |

**What we're NOT using**: GIFs, massive sprite sheets, hardcoded prompts everywhere.

## Project Architecture (Monorepo)
```
study-panda/
├── apps/
│   ├── desktop-ui/          # Electron + React frontend
│   └── assistant-core/      # Node.js backend process (IPC)
├── packages/
│   ├── animation-engine/    # Panda state machine + Rive bindings
│   ├── ai-router/           # Provider abstraction, streaming, tool parsing
│   ├── integrations/        # Calendar, email, tasks (empty until Phase 4)
│   ├── memory/              # Chat history, user profile, vector store (later)
│   └── shared-types/        # TypeScript interfaces shared across apps/packages
├── assets/                  # Rive files, sounds, themes
└── docs/
```

---

## PHASE 1 — MVP: Homework Q&A Panda (2 weeks)

**Goal**: A cute panda docked to the side of the screen that answers homework questions via text.

**Features to build**:
- Frameless, always-on-top Electron window that snaps to screen edges.
- Animated idle panda (drumming paws, occasional blink).
- Expandable side panel (click panda to reveal chat box).
- Chat input → streaming response from Claude API.
- Conversation history (persisted in SQLite).
- Markdown rendering + code highlighting (KaTeX for math).
- Copy answer button.
- Dark/light mode toggle.

**Do NOT add**:
- Email, calendar, voice, autonomous behaviour, memory system, file upload, screenshots, tool execution — nothing outside the chat.

**Core data flow**:
```
UI (React) → Assistant Controller (IPC) → AI Router → Claude/DeepSeek
```
- Streaming via Server-Sent Events or fetch `ReadableStream`.
- Abortable requests (cancel button makes panda stop "thinking").
- Provider abstraction from day one:
```ts
interface AIProvider {
  streamResponse(messages: Message[], onChunk: (text: string) => void): Promise<void>;
}
```
Implement `ClaudeProvider`, `DeepSeekProvider`, and a simple router that picks based on user setting.

**Panda states for Phase 1**:
- `idle` (tapping paws)
- `listening` (ears perk up when chat input is focused)
- `thinking` (slower taps, eyes look up)
- `responding` (paws "type" rapidly, answer appears in bubble)

---

## PHASE 2 — Make It Feel Alive (2–3 weeks)

This is **the most important phase**. Without it, you have a sidebar with a gif, not a companion.

**State machine** (use XState or a clean reducer):
- `idle` (random idle behaviours: stretch, look around, tail flick)
- `sleeping` (after inactivity, panda curls up)
- `excited` (when user comes back, when answer is ready)
- `error` (confused head tilt)
- `dragging` (user drags panda to reposition)

**Animation pipeline**:
- Rive skeletal animations driven by state machine.
- Smooth transitions (Framer Motion) for panel expand/collapse.
- Sound effects (optional, small `.ogg` files for bleats/squeaks/taps).

**Interaction details**:
- Panda can be dragged from its head to any screen edge.
- Idle after 5 min → panda falls asleep (collapses to tiny sleeping icon).
- Hover/click wakes it up.
- Subtle particles/effects when happy (hearts or sparkles) — keep it tiny to avoid annoyance.

---

## PHASE 3 — Homework Assistant (3 weeks)

Now the AI becomes genuinely useful for studying.

**New capabilities**:
- Screenshot region selection (Electron `desktopCapturer`).
- OCR pipeline: Tesseract.js (or a lightweight local model) → extract text → send to Claude with "explain this problem step-by-step".
- LaTeX rendering of math (MathJax/KaTeX).
- PDF upload (PDF.js extraction).
- Code explanation mode (detects code blocks and explains line-by-line).
- Context-aware follow-up questions.

**Workflow**:
```
User captures screen region
  → OCR extracts text
  → Context builder (adds previous messages, course info)
  → Claude generates explanation
  → Answer formatted with steps, notes, and follow-up suggestions
```

**UI additions**:
- Floating "screenshot" button next to panda.
- Explanation panel with expandable steps.
- "Teach me" mode where the panda asks follow-up questions (Socratic method).

---

## PHASE 4 — Productivity Integrations (3–4 weeks)

**Now** add calendar, email, and task reminders — with **strict security**.

**Architecture**:
- The AI **never** calls APIs directly.
- Instead, the LLM outputs structured intent:
```json
{
  "tool": "calendar.create_event",
  "title": "Math Midterm",
  "time": "2026-05-25T15:00"
}
```
- A **Tool Executor** validates permissions, required fields, and performs the action.
- User must explicitly authorise each integration (OAuth2, stored with Electron's `safeStorage`).

**Features**:
- **Calendar**: show today's events, "add event" via chat, 10-min reminders (panda bounces and shows event).
- **Email**: unread count badge on panda's collar, last 5 unread subject lines, click to open in browser. Panda can summarise an email if you paste it (no reading your inbox automatically).
- **Tasks**: local to-do list stored in SQLite, panda reminds you of due items.
- **Daily agenda**: panda says "Good morning! You have 2 events and 1 task due today."

**Safety rules**:
- Never auto-send emails.
- Never delete calendar events without confirmation.
- All tool calls are logged and can be revoked.

---

## PHASE 5 — Memory & Personality (4+ weeks)

Now the panda remembers you and becomes proactive.

**Memory layers**:
- **Short-term**: conversation history (already in SQLite).
- **Long-term**: vector embeddings (LanceDB or Chroma) of past discussions, courses, preferences.
- **User profile**: your name, what you study, sleep schedule, preferred tone.

**Behaviours**:
- "Last time you were stuck on integrals — need more practice?"
- "You have a deadline tomorrow. Want me to quiz you?"
- Panda adapts personality (e.g., encourages a stressed user more gently).

**Implementation**:
- Use Claude to summarise and extract key facts from conversations → store in vector DB.
- Periodic background jobs to update profile (never blocking UI).

---

## PHASE 6 — Advanced (Ongoing)

Only after everything above is stable:
- Voice input (whisper.cpp or browser SpeechRecognition).
- Wake word ("Hey Panda").
- Local small model for offline fallback (e.g., Ollama with tiny model).
- Multi-agent orchestration (study planner + scheduler + motivator agents).
- RAG over your own notes/PDFs.
- Plug-in system for community integrations.

---

## AI-Assisted Development Workflow

You'll code with Claude and DeepSeek — here's the disciplined approach:

1. **You** define the architecture and approve every module.
2. **Claude** designs the module plan, writes complex logic, debugs, and refactors.
3. **DeepSeek** generates boilerplate: UI components, repetitive API wrappers, CSS templates.
4. **You** review every line before merging — never paste blindly.

### First 10 Tasks (Actionable Now)
1. Fork `Edge-Panel`, clean the repo, remove all old UI.
2. Convert to TypeScript, set up monorepo structure with `apps/` and `packages/`.
3. Create React state architecture with Zustand or React Context + reducer.
4. Implement `AIProvider` abstraction with streaming support.
5. Build streaming chat interface (input, bubble list, markdown rendering).
6. Build animated panda container using Rive (idle tap + blink as starting animation).
7. Add `thinking` and `typing` states triggered by chat flow.
8. Persist conversations locally with SQLite.
9. Add screenshot region capture + OCR pipeline (Tesseract.js).
10. Add structured tool execution system (intent parser → validator → executor).

---

## Realistic Timeline

| Phase | Duration |
|-------|----------|
| MVP (chat + panda) | 2–4 weeks |
| Make it feel alive | +2–3 weeks |
| Homework assistant | +3 weeks |
| Productivity tools | +3–4 weeks |
| Memory & personality | +4 weeks |
| Advanced features | ongoing |

Expect a **polished, impressive companion** in roughly 3–4 months of consistent work. The interaction quality and animation detail are what will make this project stand out — not just the AI.

---

If you want, I can expand any phase into a detailed task list with exact file structure, API request schemas, or the Rive animation spec to hand off to your animator (or AI generator). Just let me know which part you're tackling next.
