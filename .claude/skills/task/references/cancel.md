# Mode: cancel

## Input
```
/task cancel              -> Cancel the current active task
/task cancel <task-name>  -> Cancel a specific task
```

## Process

1. **Ask for reason** (if not clear from context)
2. **Cancel via task engine:**
   ```bash
   python .task-engine/task.py cancel --task "Task name" --reason "Why cancelled"
   ```
3. **Git backup:** Same as complete mode
4. **Confirm:** `Task cancelled: [Task Name] -> archived`

## Important
- No reconciliation check needed. No docs check either.
- Document cancellation reason in Work Done section (manually, via Edit). Include relationship to any replacing task.
- Output files from partial work stay in `outputs/` unless explicitly asked to archive.
