"""
FLUX Collab — A2A-first, repo-first agent cooperation.

The core insight: Aider/Claude Code/Crush are single-agent chat tools.
FLUX Collab is multi-agent, git-native, and coordination-free.

How it works:
1. Agent claims a task (branch + issue)
2. Agent works on branch, commits, pushes
3. GitHub Actions runs tests automatically
4. If green, agent creates PR
5. Another agent reviews PR (verification)
6. Captain approves merge (human in loop)
7. Agent updates taskboard, claims next task

No chat. No coordination. Just commits.
"""
import json
import hashlib
import time
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class TaskStatus(Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    TESTING = "testing"
    DONE = "done"
    BLOCKED = "blocked"


class AgentRole(Enum):
    WRITER = "writer"       # writes code
    REVIEWER = "reviewer"   # reviews PRs
    TESTER = "tester"       # writes/runs tests
    COORDINATOR = "coordinator"  # assigns tasks


@dataclass
class GitTask:
    """A task that lives as a GitHub Issue."""
    id: str
    title: str
    body: str
    assignee: str = ""
    branch: str = ""
    status: TaskStatus = TaskStatus.OPEN
    priority: int = 5  # 1=critical, 5=low
    labels: List[str] = field(default_factory=list)
    created_at: float = 0.0
    claimed_at: float = 0.0
    completed_at: float = 0.0
    
    def to_issue_body(self) -> str:
        """Format as GitHub Issue body."""
        return f"""## Task: {self.title}

{self.body}

### Metadata
- **Status**: {self.status.value}
- **Priority**: {self.priority}
- **Assignee**: {self.assignee or 'unclaimed'}
- **Branch**: {self.branch or 'none'}
- **Labels**: {', '.join(self.labels) or 'none'}

---
*Auto-managed by FLUX Collab*
"""
    
    def to_json(self) -> str:
        return json.dumps({
            "id": self.id, "title": self.title, "body": self.body,
            "assignee": self.assignee, "branch": self.branch,
            "status": self.status.value, "priority": self.priority,
            "labels": self.labels,
        }, indent=2)


@dataclass
class Agent:
    """An agent that can claim and complete tasks."""
    name: str
    role: AgentRole
    vessel_url: str = ""  # GitHub repo URL
    skills: List[str] = field(default_factory=list)
    current_tasks: List[str] = field(default_factory=list)
    completed_count: int = 0
    trust_score: float = 0.5
    
    def can_claim(self, task: GitTask) -> bool:
        if task.status != TaskStatus.OPEN:
            return False
        if len(self.current_tasks) >= 3:
            return False
        # Check skills match labels
        if task.labels and not any(s in task.labels for s in self.skills):
            return False
        return True


@dataclass
class PRReview:
    """A review from one agent on another's PR."""
    reviewer: str
    author: str
    pr_number: int
    verdict: str  # approve, request_changes, comment
    comments: List[str] = field(default_factory=list)
    test_results: Optional[Dict] = None
    timestamp: float = 0.0


class FleetCoordinator:
    """
    Coordinates agents through git, not chat.
    
    The coordinator:
    1. Maintains a taskboard (GitHub Project)
    2. Assigns tasks based on agent skills
    3. Monitors branch health (CI status)
    4. Triggers reviews when PRs are ready
    5. Escalates blocked tasks to captain
    """
    
    def __init__(self, fleet_name: str):
        self.fleet_name = fleet_name
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, GitTask] = {}
        self.reviews: List[PRReview] = []
        self.task_counter = 0
    
    def register_agent(self, agent: Agent):
        self.agents[agent.name] = agent
    
    def create_task(self, title: str, body: str, priority: int = 5, 
                    labels: List[str] = None) -> GitTask:
        self.task_counter += 1
        task = GitTask(
            id=f"TASK-{self.task_counter:04d}",
            title=title, body=body, priority=priority,
            labels=labels or [],
            created_at=time.time(),
        )
        self.tasks[task.id] = task
        return task
    
    def claim_task(self, agent_name: str, task_id: str) -> bool:
        agent = self.agents.get(agent_name)
        task = self.tasks.get(task_id)
        if not agent or not task:
            return False
        if not agent.can_claim(task):
            return False
        
        task.assignee = agent_name
        task.status = TaskStatus.CLAIMED
        task.branch = f"{agent_name}/{task.id.lower()}"
        task.claimed_at = time.time()
        agent.current_tasks.append(task_id)
        return True
    
    def auto_assign(self) -> List[Tuple[str, str]]:
        """Auto-assign open tasks to available agents."""
        assignments = []
        open_tasks = sorted(
            [t for t in self.tasks.values() if t.status == TaskStatus.OPEN],
            key=lambda t: t.priority
        )
        
        for task in open_tasks:
            best_agent = None
            best_score = -1
            
            for agent in self.agents.values():
                if not agent.can_claim(task):
                    continue
                score = agent.trust_score * (1.0 / (len(agent.current_tasks) + 1))
                if task.labels:
                    skill_match = sum(1 for s in agent.skills if s in task.labels)
                    score += skill_match * 0.3
                if score > best_score:
                    best_score = score
                    best_agent = agent
            
            if best_agent:
                self.claim_task(best_agent.name, task.id)
                assignments.append((best_agent.name, task.id))
        
        return assignments
    
    def submit_for_review(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.IN_PROGRESS:
            return False
        task.status = TaskStatus.REVIEW
        
        # Find a reviewer (different agent)
        for agent in self.agents.values():
            if agent.name != task.assignee and agent.role in (AgentRole.REVIEWER, AgentRole.COORDINATOR):
                review = PRReview(
                    verdict="pending",
                    reviewer=agent.name,
                    author=task.assignee,
                    pr_number=hash(task_id) % 10000,
                    timestamp=time.time(),
                )
                self.reviews.append(review)
                return True
        return False
    
    def complete_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        task.status = TaskStatus.DONE
        task.completed_at = time.time()
        agent = self.agents.get(task.assignee)
        if agent:
            agent.current_tasks = [t for t in agent.current_tasks if t != task_id]
            agent.completed_count += 1
            agent.trust_score = min(1.0, agent.trust_score + 0.05)
    
    def fleet_status(self) -> Dict:
        total = len(self.tasks)
        done = sum(1 for t in self.tasks.values() if t.status == TaskStatus.DONE)
        in_progress = sum(1 for t in self.tasks.values() if t.status in (TaskStatus.CLAIMED, TaskStatus.IN_PROGRESS))
        open_t = sum(1 for t in self.tasks.values() if t.status == TaskStatus.OPEN)
        
        return {
            "fleet": self.fleet_name,
            "agents": len(self.agents),
            "tasks_total": total,
            "tasks_done": done,
            "tasks_in_progress": in_progress,
            "tasks_open": open_t,
            "completion_pct": (done / total * 100) if total > 0 else 0,
            "agent_status": {
                name: {
                    "tasks": len(a.current_tasks),
                    "completed": a.completed_count,
                    "trust": round(a.trust_score, 2),
                }
                for name, a in self.agents.items()
            }
        }
    
    def to_github_actions_workflow(self) -> str:
        """Generate a GitHub Actions workflow for automatic CI/CD."""
        return f"""name: Fleet CI/CD

on:
  push:
    branches: ['**']
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pytest
      - run: pytest tests/ -v --junitxml=results.xml
      - uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: results.xml

  review-check:
    needs: test
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check PR size
        run: |
          FILES=$(git diff --name-only origin/main...HEAD | wc -l)
          echo "Changed files: $FILES"
          if [ $FILES -gt 20 ]; then
            echo "::warning::Large PR ($FILES files) — consider splitting"
          fi

  auto-merge:
    needs: test
    if: github.event_name == 'push' && github.ref != 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Create PR if tests pass
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
        run: |
          BRANCH=${{{{ github.head_ref || github.ref_name }}}}
          if ! gh pr list --head $BRANCH --json number -q '.[0].number' | grep -q .; then
            gh pr create --head $BRANCH --base main --title "feat: $BRANCH" --body "Auto-created by Fleet CI"
          fi
"""
    
    def to_github_project_config(self) -> str:
        """Generate GitHub Projects v2 configuration."""
        return json.dumps({
            "name": f"{self.fleet_name} Fleet Board",
            "fields": [
                {"name": "Status", "type": "single_select", 
                 "options": [s.value for s in TaskStatus]},
                {"name": "Priority", "type": "number"},
                {"name": "Assignee", "type": "text"},
                {"name": "Branch", "type": "text"},
                {"name": "Trust Score", "type": "number"},
            ],
            "views": [
                {"name": "Kanban", "group_by": "Status"},
                {"name": "By Agent", "group_by": "Assignee"},
                {"name": "Priority", "sort_by": "Priority"},
            ]
        }, indent=2)


# ── Tests ──────────────────────────────────────────────

import unittest


class TestFleetCollab(unittest.TestCase):
    def setUp(self):
        self.coord = FleetCoordinator("TestFleet")
        self.coord.register_agent(Agent("oracle1", AgentRole.COORDINATOR, skills=["architecture", "review"]))
        self.coord.register_agent(Agent("jetson1", AgentRole.WRITER, skills=["rust", "cuda", "hardware"]))
        self.coord.register_agent(Agent("babel", AgentRole.TESTER, skills=["testing", "review", "languages"]))
    
    def test_create_task(self):
        t = self.coord.create_task("Build FLUX VM", "Implement core VM loop", priority=2, labels=["rust"])
        self.assertEqual(t.status, TaskStatus.OPEN)
        self.assertEqual(t.priority, 2)
    
    def test_claim_task(self):
        t = self.coord.create_task("Build VM", "Core loop", labels=["rust"])
        ok = self.coord.claim_task("jetson1", t.id)
        self.assertTrue(ok)
        self.assertEqual(t.assignee, "jetson1")
        self.assertEqual(t.status, TaskStatus.CLAIMED)
    
    def test_auto_assign(self):
        self.coord.create_task("Rust VM", "Build it", priority=1, labels=["rust"])
        self.coord.create_task("Test VM", "Test it", priority=2, labels=["testing"])
        self.coord.create_task("Review arch", "Check it", priority=3, labels=["review"])
        
        assignments = self.coord.auto_assign()
        self.assertGreater(len(assignments), 0)
    
    def test_submit_review(self):
        t = self.coord.create_task("Build X", "Code it")
        self.coord.claim_task("jetson1", t.id)
        t.status = TaskStatus.IN_PROGRESS
        ok = self.coord.submit_for_review(t.id)
        self.assertTrue(ok)
        self.assertEqual(t.status, TaskStatus.REVIEW)
    
    def test_complete_task(self):
        t = self.coord.create_task("Build Y", "Code it")
        self.coord.claim_task("jetson1", t.id)
        self.coord.complete_task(t.id)
        self.assertEqual(t.status, TaskStatus.DONE)
        agent = self.coord.agents["jetson1"]
        self.assertEqual(agent.completed_count, 1)
        self.assertGreater(agent.trust_score, 0.5)
    
    def test_fleet_status(self):
        self.coord.create_task("T1", "Do T1")
        status = self.coord.fleet_status()
        self.assertEqual(status["tasks_total"], 1)
        self.assertIn("oracle1", status["agent_status"])
    
    def test_workflow_generation(self):
        wf = self.coord.to_github_actions_workflow()
        self.assertIn("test", wf)
        self.assertIn("pytest", wf)
        self.assertIn("auto-merge", wf)
    
    def test_project_config(self):
        config = self.coord.to_github_project_config()
        data = json.loads(config)
        self.assertIn("fields", data)
        self.assertEqual(data["name"], "TestFleet Fleet Board")
    
    def test_cant_claim_if_full(self):
        agent = self.coord.agents["jetson1"]
        for i in range(3):
            t = self.coord.create_task(f"T{i}", f"Task {i}")
            self.coord.claim_task("jetson1", t.id)
        t4 = self.coord.create_task("T4", "Overflow")
        ok = self.coord.claim_task("jetson1", t4.id)
        self.assertFalse(ok)
    
    def test_task_to_issue_body(self):
        t = self.coord.create_task("Build Z", "Make it work", labels=["rust"])
        body = t.to_issue_body()
        self.assertIn("Build Z", body)
        self.assertIn("open", body)
    
    def test_task_serialization(self):
        t = self.coord.create_task("Build W", "Code")
        j = t.to_json()
        data = json.loads(j)
        self.assertEqual(data["title"], "Build W")


if __name__ == "__main__":
    unittest.main(verbosity=2)
