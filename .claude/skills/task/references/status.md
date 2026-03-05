# Mode: status

## Process

1. **Read via task engine:**
   ```bash
   python .task-engine/task.py list
   ```
2. Display summary to user:
   ```
   **Active:** [task name(s)] or (none)
   **Paused:** [count] tasks
     1-next: [task names]
     2-blocked: [task names]
     3-later: [task names]
     4-someday: [task names]
     unset: [task names, if any]
   **Recurring:** [count] processes
   **Ideas:** [count] tasks
   ```
   The paused breakdown by priority helps the user see the return queue at a glance. List output is already sorted by priority.
