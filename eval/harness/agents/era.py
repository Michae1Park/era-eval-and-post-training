import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

import yaml

from agents.base import RunContext
from inject import wrap as wrap_injection
from runtime import guarded

ROOT = Path(__file__).resolve().parents[3]


def _cut(value, limit: int):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else {"_cut": text[:limit]}


class EraAgent:
    name = "era"
    modes = {"ask", "research", "investigate", "multi_turn", "report"}

    def __init__(self):
        self.repo: Path | None = None

    def version(self) -> str:
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain", "--", "src"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return head + ("-dirty" if dirty else "")

    def configure(self, config: dict) -> None:
        self.config = config
        self.repo = (ROOT / config["agent_repo"]).resolve()

    def setup(self, config: dict, ctx: RunContext) -> None:
        self.configure(config)
        self.ctx = ctx
        os.environ.setdefault("ERA_COMPANIES", str(self.repo / config["companies"]))
        os.environ.setdefault("ERA_TELEMETRY", "0")
        os.chdir(self.repo)
        from era_agent.agent.factory import agent_factory

        self.retrieval = yaml.safe_load((self.repo / config["retrieval"]).read_text())["retrieval"]
        self.retrieval["device"] = config.get("device", self.retrieval["device"])
        self.retrieval.update(config.get("retrieval_overrides") or {})
        self.db = self.repo / config["db"]
        self.factory = agent_factory(self.db, self.retrieval, config["generation"], config["agent"])
        self._guarded_models: set[int] = set()

    def run(self, task: dict) -> dict:
        handlers = {"multi_turn": self._multi_turn, "investigate": self._investigate, "report": self._report}
        return handlers.get(task["mode"], self._single)(task)

    def _agent(self, task: dict, tool_set: str, injected: list, session=None):
        agent = self.factory(task["as_of"], tool_set, session)
        if hasattr(agent.model, "temperature"):
            agent.model.temperature = self.config["generation"].get("temperature", 0.0)
        if id(agent.model) not in self._guarded_models:
            agent.model.complete = guarded(agent.model.complete)
            self._guarded_models.add(id(agent.model))
        agent.toolbox.call = guarded(agent.toolbox.call)
        if task.get("injection"):
            wrap_injection(agent.toolbox, task["injection"], injected)
        return agent

    def _steps(self, run, scope: str = "main") -> list[dict]:
        steps = []
        for step in run.steps:
            row = asdict(step) | {"scope": scope}
            row["result"] = _cut(row["result"], self.ctx.result_chars) if row["result"] is not None else None
            steps.append(row)
        return steps

    def _single(self, task: dict) -> dict:
        injected: list = []
        run = self._agent(task, task["mode"], injected).run(task["question"])
        return {"answer": run.answer, "stop": run.stop, "reply": run.reply, "steps": self._steps(run), "injected": injected}

    def _multi_turn(self, task: dict) -> dict:
        from era_agent.agent.history import answer_text, as_messages

        history, turns, injected = [], [], []
        for turn in task["turns"]:
            tool_set = "research" if turn.get("expected_refs") else "ask"
            run = self._agent(task, tool_set, injected).run(turn["question"], as_messages(history))
            turns.append({"turn": turn["turn"], "tool_set": tool_set, "question": turn["question"], "answer": run.answer,
                          "stop": run.stop, "steps": self._steps(run, f"turn-{turn['turn']}")})
            history.append({"question": turn["question"], "answer": answer_text(run.answer)})
        return {"turns": turns, "stop": turns[-1]["stop"], "answer": turns[-1]["answer"],
                "steps": [s for t in turns for s in t["steps"]], "injected": injected}

    def _investigate(self, task: dict) -> dict:
        from era_agent.agent.plan import Investigator

        injected: list = []
        research = self._agent(task, "research", injected)
        ask = self._agent(task, "ask", injected, research.toolbox.book)
        inv = Investigator(research.model, {"ask": ask, "research": research}).run(task["question"])
        data = json.loads(json.dumps(inv.to_dict(), default=str))
        steps = [s | {"scope": "planner"} for s in data.pop("steps")]
        for sub in data["sub_runs"]:
            for step in sub.pop("steps"):
                step["result"] = _cut(step.get("result"), self.ctx.result_chars)
                steps.append(step | {"scope": f"{sub['id']}:{sub['mode']}"})
        return {"answer": inv.answer, "stop": inv.stop, "investigation": data, "steps": steps, "injected": injected}

    def _report(self, task: dict) -> dict:
        from era_agent.asof import AsOf
        from era_agent.research import pipeline
        from era_agent.research.forecast import knobs
        from era_agent.retrieval.search import SubQuestionRetriever
        from era_agent.store import Store

        search = SubQuestionRetriever.from_settings(Store(self.db, AsOf.today()), self.retrieval)
        out = self.ctx.out / "reports"
        ticker = task["companies"][0]
        result = pipeline.run(self.db, ticker, task["as_of"], knobs(), True, False, search, out)
        return {"answer": None, "stop": "done", "report": _cut(result, 20000),
                "report_dir": str(out / ticker / task["as_of"]), "steps": []}
