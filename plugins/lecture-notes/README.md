# Lecture Notes — Omi Plugin

A webhook-based Omi plugin that transforms recorded conversations into structured academic notes. When a conversation ends, the plugin analyzes the transcript for educational content and returns organized notes with key concepts, definitions, topics, action items, and study tips.

## How It Works

1. You attend a lecture, study session, or academic discussion with Omi recording
2. When the conversation ends, Omi sends the transcript to this plugin
3. The plugin runs a two-stage analysis:
   - **Heuristic pre-filter**: Scores the conversation using keyword density, speaker asymmetry (lectures have one dominant speaker), duration, and content volume to skip non-academic conversations without burning API tokens
   - **LLM extraction**: Uses GPT-4o with structured output to extract key concepts, topics, summaries, questions, action items, and study tips
4. Structured notes are returned as a notification in the Omi app

## Quick Start

```bash
# Clone and navigate
cd plugins/lecture-notes

# Set up environment
cp .env.template .env
# Edit .env and add your OpenAI API key

# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

The server starts at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive API docs.

## Connect to Omi

1. Open Omi app → Settings → Enable Developer Mode
2. Go to Developer Settings → Memory Creation Webhook
3. Enter your webhook URL: `https://your-server.com/lecture-notes`
   - For local testing, use [ngrok](https://ngrok.com): `ngrok http 8000`, then use the ngrok URL
4. Start a conversation — when it ends, the plugin processes it automatically

## Example Output

For a lecture on operating systems:

```
LECTURE NOTES | Operating Systems

Summary
Introduction to process scheduling in operating systems, covering the key algorithms
used to manage CPU time allocation among competing processes.

Key Concepts
  - Process: A program in execution with its own address space and resources
  - Context Switch: The mechanism of saving and restoring process state when switching CPU allocation
  - Round Robin: A scheduling algorithm that assigns equal time slices to each process in circular order
  - Priority Scheduling: An algorithm that assigns CPU time based on process priority levels
  - Starvation: A condition where low-priority processes never receive CPU time

Topics Covered
  - Process lifecycle and states
  - CPU scheduling algorithms (FCFS, SJF, Round Robin, Priority)
  - Preemptive vs non-preemptive scheduling
  - Scheduling metrics (turnaround time, waiting time, throughput)

Questions to Explore
  - How does the Linux kernel implement its CFS (Completely Fair Scheduler)?
  - What are the tradeoffs between time slice length in Round Robin?

Action Items
  - Read Chapter 5 of Silberschatz (Process Scheduling)
  - Complete Problem Set 3 by Friday
  - Review FCFS vs SJF scheduling examples before next lab

Study Tips
  - Draw state diagrams for each scheduling algorithm with concrete numeric examples
  - Compare algorithms using a table with columns for throughput, turnaround, and waiting time
  - Practice Gantt chart problems — they appear frequently on exams
```

## Test Payload

Use this to test the endpoint locally:

```bash
curl -X POST http://localhost:8000/lecture-notes \
  -H "Content-Type: application/json" \
  -d '{
    "created_at": "2025-02-09T14:30:00Z",
    "started_at": "2025-02-09T13:00:00Z",
    "finished_at": "2025-02-09T14:15:00Z",
    "transcript_segments": [
      {"text": "Today we are going to cover process scheduling in operating systems.", "speaker": "SPEAKER_00", "is_user": false, "start": 0.0, "end": 5.0},
      {"text": "A process is a program in execution. It has its own address space, program counter, and set of resources.", "speaker": "SPEAKER_00", "is_user": false, "start": 5.0, "end": 12.0},
      {"text": "When the OS switches between processes, it performs a context switch, saving and restoring the process state.", "speaker": "SPEAKER_00", "is_user": false, "start": 12.0, "end": 20.0},
      {"text": "Let us look at the main scheduling algorithms. First, First Come First Served, or FCFS.", "speaker": "SPEAKER_00", "is_user": false, "start": 20.0, "end": 28.0},
      {"text": "FCFS is the simplest approach. Processes are executed in the order they arrive in the ready queue.", "speaker": "SPEAKER_00", "is_user": false, "start": 28.0, "end": 35.0},
      {"text": "The problem with FCFS is the convoy effect. Short processes wait behind long ones.", "speaker": "SPEAKER_00", "is_user": false, "start": 35.0, "end": 42.0},
      {"text": "Next is Shortest Job First, SJF. This algorithm selects the process with the smallest execution time.", "speaker": "SPEAKER_00", "is_user": false, "start": 42.0, "end": 50.0},
      {"text": "SJF is optimal for minimizing average waiting time, but it requires knowing burst times in advance.", "speaker": "SPEAKER_00", "is_user": false, "start": 50.0, "end": 58.0},
      {"text": "Round Robin assigns equal time slices, called quanta, to each process in a circular order.", "speaker": "SPEAKER_00", "is_user": false, "start": 58.0, "end": 66.0},
      {"text": "The choice of quantum size matters. Too small means too many context switches. Too large and it degrades to FCFS.", "speaker": "SPEAKER_00", "is_user": false, "start": 66.0, "end": 75.0},
      {"text": "Priority scheduling assigns CPU time based on priority levels. But this can cause starvation of low priority processes.", "speaker": "SPEAKER_00", "is_user": false, "start": 75.0, "end": 85.0},
      {"text": "Professor, what about the Linux scheduler?", "speaker": "SPEAKER_01", "is_user": true, "start": 85.0, "end": 88.0},
      {"text": "Great question. Linux uses the Completely Fair Scheduler. It models an ideal multitasking CPU using a red-black tree.", "speaker": "SPEAKER_00", "is_user": false, "start": 88.0, "end": 97.0},
      {"text": "For next class, read Chapter 5 of Silberschatz and complete Problem Set 3 by Friday.", "speaker": "SPEAKER_00", "is_user": false, "start": 97.0, "end": 105.0}
    ],
    "structured": {
      "title": "Process Scheduling in Operating Systems",
      "overview": "Lecture covering CPU scheduling algorithms including FCFS, SJF, Round Robin, and Priority Scheduling.",
      "emoji": "🖥️",
      "category": "education"
    },
    "discarded": false
  }'
```

## Deployment

### Render

1. Push to a GitHub repo
2. Create a new Web Service on [Render](https://render.com)
3. Set environment variables (`OPENAI_API_KEY`)
4. Deploy — Render auto-detects the Dockerfile

### Docker

```bash
docker build -t lecture-notes .
docker run -p 8000:8000 --env-file .env lecture-notes
```

### Railway

```bash
railway init
railway up
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Plugin info and available endpoints |
| `/health` | GET | Health check |
| `/lecture-notes` | POST | Memory creation trigger — receives conversation, returns structured notes |
| `/docs` | GET | Interactive API documentation (Swagger UI) |
