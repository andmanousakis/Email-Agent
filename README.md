<!-- README.md-->

# Email Agent

Prototype AI email assistant that analyzes email threads, generates draft replies, proposes actions, and requires human approval before execution.

The system demonstrates a modular architecture combining LLM reasoning, workflow orchestration, mock tool execution, and observability.

## How-To-Run

For DEMO purposes, a UI was built.

1. Clone the branch:
```bash
git clone --branch main --single-branch git@github.com:andmanousakis/Email-Agent.git
```

2. Create .env from .env.example and paste a Gemini API key:
```bash
2. Create .env from .env.example:
```

3. Build and run:
```bash
make stack-build-up
```

4. Open the UI:
```bash
http://localhost:8501
```

5. If you want to clean project images and containers:
```bash
make clean-all
```

**Note:** For more commands enter make help.


