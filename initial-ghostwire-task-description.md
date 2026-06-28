# GHOSTWIRE — Corporate Intelligence Grid

> **"Information is currency. Insight is power. Alignment is survival."**

This system turns raw company data into operational advantage — client-facing, employee-facing, and internal command-level.

---

## Table of Contents

1. [Objective](#1-objective)
2. [System Architecture](#2-system-architecture)
3. [Module 1 — Public AI Chatbot](#3-module-1--public-ai-chatbot)
4. [Module 2 — Feedback Intelligence Engine](#4-module-2--feedback-intelligence-engine)
5. [Module 3 — AI Team Assembler](#5-module-3--ai-team-assembler)
6. [Shared Components](#6-shared-components)
7. [Frontend Interfaces](#7-frontend-interfaces)
8. [Tech Stack](#8-tech-stack)
9. [Non-Functional Requirements](#9-non-functional-requirements)
10. [MVP Scope](#10-mvp-scope)
11. [Failure Conditions](#11-failure-conditions)
12. [Cyberpunk Directive](#12-cyberpunk-directive)

---

## 1. Objective

Build an AI-powered platform that:

- Acts as a **public-facing AI agent** (clients + candidates)
- Processes **internal human feedback** into actionable intelligence
- **Automatically assembles optimal teams** for new projects

All powered by a **shared intelligence layer**.

---

## 2. System Architecture

**Core Principle: One brain, multiple interfaces**

### 2.1 Knowledge Core (Central AI Layer)

This is the backbone. All features depend on it.

**Data Domains:**

| Domain | Description |
|---|---|
| Company data | Website, case studies |
| Job openings | Current open positions |
| Employee profiles | CVs, skills, history |
| Feedback data | Performance reviews |
| Project requirements | Scoped requirements per project |

**Storage:**

- **Structured DB:** PostgreSQL
- **Vector DB:** Weaviate / Pinecone

**Responsibilities:**

- Semantic search
- Context retrieval (RAG)
- Feature extraction
- Scoring & summarization

---

## 3. Module 1 — Public AI Chatbot

> **Interface:** Embedded on website (godeltech.com)

### Capabilities

**For Clients:**
- Company overview
- Case studies
- Tech expertise
- Delivery models

**For Candidates:**
- Open positions
- Requirements
- Application guidance

### Architecture

**Input:** Natural language query

**Pipeline:**
1. Intent detection *(client vs. candidate)*
2. Retrieve context *(RAG)*
3. Generate response via Claude

### Claude Prompt Spec

```
SYSTEM:
You are a corporate AI agent representing a high-end software engineering company.
Tone: confident, precise, human — not robotic.

RULES:
- Never hallucinate capabilities
- Use only provided context
- If unsure → ask clarification

USER:
<query>

CONTEXT:
<retrieved documents>

OUTPUT:
Clear, structured answer
```

### Constraints

- Response time **< 2s**
- Grounded answers only *(no hallucinations)*

---

## 4. Module 2 — Feedback Intelligence Engine

> **Raw feedback is noise. Insight is signal.**

### Input

- Peer reviews
- Manager reviews
- Self-assessments

### Output

**For Team Managers (TM):**
- Summary of strengths
- Key concerns
- Behavioral patterns
- Risk signals *(burnout, conflict)*

### Processing Pipeline

```
Text ingestion
    → Sentiment analysis
    → Theme extraction
    → Pattern detection
    → Summary generation (Claude)
```

### Claude Prompt Spec

```
SYSTEM:
You are an organizational intelligence AI.

TASK:
Analyze performance feedback and extract:
- strengths
- weaknesses
- behavioral signals
- risks

RULES:
- Be objective
- Avoid vague statements
- Highlight patterns across multiple inputs

INPUT:
<feedback set>

OUTPUT:
Structured summary
```

### Output Schema

```json
{
  "strengths": [],
  "weaknesses": [],
  "risks": [],
  "team_dynamics_signals": [],
  "confidence_score": 0.0
}
```

---

## 5. Module 3 — AI Team Assembler

> **Wrong team, wrong outcome. Always.**

### Input

- New project description
- Requirements
- Constraints *(timeline, budget, timezone)*

### Data Used

- Employee profiles
- Past project history
- Feedback intelligence
- Skill vectors

### Pipeline

**Step 1 — Project Analysis**

Claude extracts:
- Required skills
- Seniority levels
- Team composition
- Risk factors

**Step 2 — Candidate Scoring**

| Dimension | Method |
|---|---|
| Skill Match | Embeddings |
| Experience Fit | Rule-based |
| Feedback Score | Derived metric |
| Availability | Scheduling data |
| Team Compatibility | Graph-based |

**Step 3 — Team Optimization**

Goal: Maximize:
- Skill coverage
- Collaboration probability
- Delivery success likelihood

### Output Schema

```json
{
  "team": [
    {
      "employee_id": "uuid",
      "role": "backend",
      "match_score": 0.92
    }
  ],
  "gaps": [],
  "risks": [],
  "alternatives": []
}
```

### Claude Prompt Spec

```
SYSTEM:
You are a high-level technical staffing AI.

TASK:
Select the best possible team for a project.

CRITERIA:
- Skills
- Experience
- Feedback signals
- Team synergy

OUTPUT:
- team selection
- reasoning
- risks
```

---

## 6. Shared Components

### 6.1 Employee Intelligence Profile

Unified model combining:
- CV data
- Skills
- Feedback summaries
- Project history

### 6.2 Embedding Layer

Used across:
- Chatbot (RAG)
- Matching
- Feedback clustering

### 6.3 Explainability Engine

Every decision must output:
- **Why this answer**
- **Why this person/team**

---

## 7. Frontend Interfaces

| Type | Interface |
|---|---|
| Public | Chat widget |
| Internal | Feedback dashboard |
| Internal | Team assembly UI |

---

## 8. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python (FastAPI) |
| Frontend | React |
| AI | Claude API |
| Vector DB | Weaviate / Pinecone |
| Infrastructure | GCP |

---

## 9. Non-Functional Requirements

- **GDPR compliant** *(critical)*
- Role-based access control
- Audit logs for AI decisions
- No exposure of sensitive employee data externally

---

## 10. MVP Scope

Deliver first:

- [ ] Chatbot *(RAG-based)*
- [ ] Feedback summarization
- [ ] Basic team matching *(no optimization yet)*

---

## 11. Failure Conditions

The system **fails** if:

- Chatbot hallucinates
- Feedback summaries are generic
- Team selection ignores behavioral data
- Modules operate independently *(no shared intelligence)*

---

## 12. Cyberpunk Directive

> This is not a chatbot. Not an HR tool. Not a recommender.  
> **This is a decision system operating inside a corporate battlefield.**

| Condition | Verdict |
|---|---|
| It only retrieves data | Dead weight |
| It doesn't influence decisions | Irrelevant |
| It can't explain itself | Can't be trusted |

**Directive: Build intelligence, not features.**
