# KB Support Agent

AI-powered support assistant with knowledge base search and ticket creation capabilities.

## Overview

This project implements an AI agent that helps users find answers in a knowledge base and creates support tickets when needed. It uses OpenAI's function calling API to interact with tools (`search_kb` and `create_ticket`) and provides a modern web interface for user interaction.

## Features

- **Knowledge Base Search**: Search through internal knowledge base articles using keyword matching with scoring
- **Ticket Creation**: Automatically create support tickets when KB doesn't contain relevant information
- **Multilingual Support**: Basic Russian-to-English translation for keyword-based search
- **Web Interface**: Modern, responsive web UI with dark theme
- **Chat History**: View conversation history and thread management
- **Observability**: Logging of all tool calls and responses for debugging and QA

## Architecture

### Backend
- **Framework**: FastAPI
- **AI Model**: OpenAI GPT (Chat Completions API)
- **Database**: SQLite for logging agent runs
- **Tools**: Function calling for `search_kb` and `create_ticket`

### Frontend
- **Technology**: Vanilla HTML, CSS, JavaScript
- **Design**: Dark theme with purple/blue accents
- **Responsive**: Mobile-friendly with hamburger menu

### Data Flow

1. **Retrieval**: User query → KB search → Relevant articles returned
2. **Generation**: Model receives KB results → Generates answer in user's language
3. **Fallback**: If no KB found → Model creates ticket via `create_ticket` tool

## Project Structure

```
agent/
├── main.py                 # FastAPI backend, agent orchestration
├── kb_seed.json            # Knowledge base (5 articles)
├── runs.db                 # SQLite database for logging
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── static/                # Frontend files
│   ├── index.html         # Main HTML
│   ├── style.css          # Styles
│   ├── script.js          # Frontend logic
│   └── *.png, *.webp      # Icons and images
├── view_history.py        # Utility to view runs.db
└── test_example.sh        # API test script
```

## Installation

1. **Clone the repository**:
```bash
git clone https://github.com/Leeesenka/IA-Agent.git
cd IA-Agent
```

2. **Create virtual environment**:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**:
Create a `.env` file in the project root:
```env
OPENAI_API_KEY=your_openai_api_key_here
```

5. **Initialize database**:
The database will be created automatically on first run.

## Usage

### Running the Server

```bash
uvicorn main:app --reload --port 8000
```

The web interface will be available at `http://localhost:8000`

### API Endpoints

- `GET /` - Web interface
- `POST /chat` - Chat endpoint (message, thread_id)
- `POST /create-ticket` - Manual ticket creation
- `GET /history` - Get conversation history
- `GET /threads` - List all thread IDs

### Example API Request

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my password?",
    "thread_id": "demo-thread"
  }'
```

### Viewing History

```bash
python view_history.py
```

## Knowledge Base

The knowledge base (`kb_seed.json`) contains 5 articles:
- Password reset
- Payment failed
- API rate limits
- Account deletion
- Two-factor authentication

Each article has:
- `id`: Unique identifier
- `title`: Article title
- `content`: Article content
- `url`: Link to full article

## How It Works

### Search Algorithm

1. **Query Normalization**: Lowercase, strip whitespace
2. **Word Matching**: Split query into words, match against KB content
3. **Scoring**: 
   - Base score: word matches in content
   - Bonus: matches in title
   - Match ratio calculation
4. **Translation**: Basic RU→EN keyword mapping for multilingual support
5. **Filtering**: Results filtered by score threshold (≥2.5) and limited to top 2

### Agent Logic

1. **Mandatory Retrieval**: Always performs `search_kb()` first
2. **Dynamic Tool Control**: 
   - If KB found with good score → Tools disabled (model cannot create ticket)
   - If KB not found or low score → Tools enabled (model can create ticket)
3. **Response Generation**: Model generates structured response with:
   - Answer summary
   - Steps from KB
   - Clarifying questions (if needed)
   - Sources (KB URLs)
   - Next steps
   - Confidence level
   - Ticket info (if created)

### Confidence Scoring

- **High**: KB found with score > 0.6
- **Medium**: KB found with score ≥ 0.3
- **Low**: No KB found or score < 0.3

## Configuration

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required)

### Constants in `main.py`

- `KB_SCORE_THRESHOLD_RAW = 2.5`: Minimum score for KB results
- `MAX_KB_RESULTS = 2`: Maximum KB results to return
- Model: `gpt-4o-mini` (configurable)

## Development

### Testing

```bash
# Test API endpoint
bash test_example.sh

# View database contents
python view_history.py
```

### Adding KB Articles

Edit `kb_seed.json` and add new articles following the existing format:

```json
{
  "id": "article_id",
  "title": "Article Title",
  "content": "Article content here...",
  "url": "https://kb.local/article-url"
}
```

## Future Improvements

- [ ] Replace keyword search with embeddings/RAG for semantic search
- [ ] Implement proper multilingual translation (not just keyword mapping)
- [ ] Add authentication and user management
- [ ] Integrate with real ticket system (Jira, Linear, Zendesk)
- [ ] Add evaluation test cases
- [ ] Implement proper error handling and retries
- [ ] Add rate limiting
- [ ] Deploy to production (Railway, Render, etc.)

## Tech Stack

- **Backend**: Python 3.8+, FastAPI, OpenAI API
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Database**: SQLite
- **Deployment**: Ready for Railway, Render, Fly.io, etc.

## License

This project is open source and available for educational purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Author

Built as a portfolio project demonstrating AI agents with function calling capabilities.
