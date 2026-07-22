# AI-Powered Frontend Generation Agent

> **Generate a complete React/Vite frontend from a UI screenshot + user stories using the Groq API.**

---

## Overview

This system takes:
1. A **reference UI screenshot** (PNG/JPG/WEBP)
2. A **user stories JSON** file

...and produces a **runnable React/Vite project** with:
- Full traceability (`data-ui-id` attributes on every element)
- Per-story component files
- Static HTML previews
- CSS matching the reference design

---

## Architecture

```
Reference Image
      ↓
Stage 1 — Image Analyzer  (Groq Vision)
      ↓ ui_spec.json
Stage 2 — Story Mapper    (Groq Text)
      ↓ story_ui_mapping.json
Stage 3 — Code Generator  (Groq Vision + Text)
      ↓
HTML + TSX/JSX + CSS → React/Vite Project
      ↓
npm install && npm run dev
```

---

## Quick Start

### 1. Clone & Install

```bash
cd "d:\New folder\Frontend\frontend-generation-agent"
pip install -r requirements.txt
```

### 2. Configure API Key

```bash
copy .env.example .env
# Edit .env and set your GROQ_API_KEY
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

### 3a. Use the Web UI (Recommended)

```bash
python ui/app_ui.py
# Open http://127.0.0.1:5000 in your browser
```

Upload your screenshot, paste your user stories JSON, click **Generate Frontend**.

### 3b. Use the CLI

```bash
python main.py \
  --image input/images/your-ui.png \
  --stories input/user_stories/stories.json \
  --project my-app \
  --lang tsx
```

### 4. Run the Generated App

```bash
cd output/my-app/react-app
npm install
npm run dev
```

---

## Project Structure

```
frontend-generation-agent/
├── .env.example          # Environment template
├── .gitignore
├── requirements.txt
├── config.py             # Centralised config (loads from .env)
├── main.py               # CLI entry point
│
├── agent/
│   ├── image_analyzer.py # Stage 1 — Vision model analysis
│   ├── story_mapper.py   # Stage 2 — Story → UI element mapping
│   └── code_generator.py # Stage 3 — React code generation
│
├── models/
│   ├── ui_spec.py        # Pydantic schema: ui_spec.json
│   ├── story_mapping.py  # Pydantic schema: story_ui_mapping.json
│   └── traceability.py   # Pydantic schema: traceability.json
│
├── utils/
│   ├── groq_client.py    # Groq SDK wrapper (vision + text)
│   ├── file_manager.py   # Output directory management
│   └── json_utils.py     # JSON parsing, fence stripping, validation
│
├── prompts/
│   ├── image_analysis.txt    # Stage 1 system prompt
│   ├── story_mapping.txt     # Stage 2 system prompt
│   └── code_generation.txt   # Stage 3 system prompt
│
├── ui/
│   ├── app_ui.py             # Flask web UI (control panel)
│   ├── templates/index.html  # Dark glassmorphism UI
│   └── static/
│       ├── style.css
│       └── app.js
│
├── input/
│   ├── images/               # Place your reference screenshots here
│   └── user_stories/         # Place your stories JSON here
│       └── sample_stories.json
│
└── output/
    └── <project-name>/
        ├── metadata/
        │   ├── ui_spec.json
        │   ├── story_ui_mapping.json
        │   └── traceability.json
        ├── static-html/
        │   └── <Page>.html
        └── react-app/
            ├── package.json
            ├── vite.config.ts
            ├── tsconfig.json
            ├── index.html
            └── src/
                ├── App.tsx
                ├── main.tsx
                ├── index.css
                ├── stories/
                │   └── US101_Login/
                │       ├── user_story.json
                │       ├── ui_mapping.json
                │       ├── LoginPage.tsx
                │       └── LoginPage.css
                └── shared/
                    └── components/
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(required)* | Your Groq API key |
| `VISION_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Vision-capable model for Stage 1 |
| `CODE_MODEL` | `llama-3.3-70b-versatile` | Text/code model for Stages 2 & 3 |
| `OUTPUT_LANGUAGE` | `tsx` | `tsx` or `jsx` |
| `OUTPUT_DIR` | `output` | Root output directory |
| `UI_HOST` | `127.0.0.1` | Web UI host |
| `UI_PORT` | `5000` | Web UI port |
| `MAX_JSON_RETRIES` | `3` | Retries for malformed LLM JSON |

---

## User Stories Format

```json
[
  {
    "id": "US101",
    "title": "User Login",
    "description": "As a user, I want to log in with email and password.",
    "acceptanceCriteria": [
      "Email field validates format",
      "Password is masked",
      "Login button submits the form"
    ]
  }
]
```

---

## Traceability

Every generated DOM element includes a `data-ui-id` attribute:

```html
<input data-ui-id="UI_EMAIL_001" type="email" />
<button data-ui-id="UI_LOGIN_BTN_001">Log In</button>
```

These IDs are consistent across:
- `ui_spec.json` → `story_ui_mapping.json` → HTML → TSX/JSX → `traceability.json`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent | Python 3.11, Groq SDK, Pydantic v2, Pillow, python-dotenv |
| Web UI (control panel) | Flask, SSE, Vanilla HTML/CSS/JS |
| Generated Frontend | React 18, Vite 5, TypeScript or JavaScript, CSS |
| AI | Groq API (vision + text models) |

---

## License

MIT
