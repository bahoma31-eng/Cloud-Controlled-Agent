#!/usr/bin/env python3
"""
main.py
~~~~~~~
Entry point for Cloud Controlled Agent V13 (Modular).

This file wires together all modules and runs the main Supervisor loop
with graceful shutdown support.

Usage:
    python main.py
"""

import signal
import sys
import time
import logging

from agent.config import (
    validate,
    POLL_SECONDS,
    MAX_RETRIES_PER_STEP,
    TASK_MOTHER_PATH,
    PLAN_PATH,
    TASKS_PATH,
    OUTBOX_DIR,
)
from agent.github_api import GitHubClient
from agent.llm_client import LLMClient
from agent.supervisor import Supervisor
from agent.state import StateManager
from agent.plan_engine import (
    default_plan,
    parse_plan,
    render_plan,
    find_next_step,
    build_task_payload,
    now_iso,
)
from agent import ui

logger = logging.getLogger("cloud-agent.main")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n\U0001f6d1 [SHUTDOWN] Graceful shutdown requested. Finishing current iteration...")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the agent main loop."""

    # --- Startup -----------------------------------------------------------
    print("\U0001f680 [INIT] Starting Cloud Controlled Agent V13...")
    validate()

    gh = GitHubClient()
    llm = LLMClient()
    supervisor = Supervisor(llm)
    state_mgr = StateManager(gh)

    ui.print_startup()
    ui.print_init_complete()

    loop_counter = 0

    # --- Loop --------------------------------------------------------------
    while not _shutdown_requested:
        try:
            loop_counter += 1
            ui.print_loop_iteration(loop_counter, now_iso())

            # Read remote files
            task_mother, _ = gh.get_file(TASK_MOTHER_PATH)
            tasks_raw, _ = gh.get_file(TASKS_PATH)
            plan_raw, _ = gh.get_file(PLAN_PATH)
            state = state_mgr.load()

            mother = (task_mother or "").strip()

            # --- Auto-reset on new mission --------------------------------
            if mother and mother.upper() not in (
                "PROCESSING", "FAILED", "WAITING", "DONE"
            ):
                print("\U0001f6a8 [MAIN] NEW MISSION DETECTED! Clean slate protocol...")
                gh.put_file(TASK_MOTHER_PATH, "PROCESSING", "Supervisor: mission accepted")
                goal = mother

                plan_raw = default_plan(goal)
                gh.put_file(PLAN_PATH, plan_raw, "Supervisor: wipe plan for new mission")

                state = state_mgr.reset()

                gh.put_file(TASKS_PATH, "waiting for tasks", "Supervisor: clear tasks")
                tasks_raw = "waiting for tasks"

                ui.print_new_mission(goal)
            else:
                if plan_raw:
                    parsed = parse_plan(plan_raw)
                    goal = parsed["meta"].get("GOAL", "").strip() or "No goal"
                else:
                    goal = "No goal"

            # Skip if idle
            if not mother or mother.lower() in ("waiting", "done"):
                time.sleep(POLL_SECONDS)
                continue

            # Ensure plan exists
            if not plan_raw or "# MISSION PLAN" not in plan_raw:
                plan_raw = default_plan(goal)
                gh.put_file(PLAN_PATH, plan_raw, "Supervisor: initialize plan")

            # --- Worker execution -----------------------------------------
            if tasks_raw and tasks_raw.strip().lower() not in (
                "waiting for tasks", "processing", "done", ""
            ):
                ui.print_worker_executing()
                from agent.worker import execute as worker_execute

                report = worker_execute(tasks_raw)
                if report:
                    report_name = f"{OUTBOX_DIR}/log_{int(time.time())}.txt"
                    gh.put_file(report_name, report, "Worker: upload execution report")
                    gh.put_file(TASKS_PATH, "waiting for tasks", "Worker: idle")

            # --- Supervisor evaluation ------------------------------------
            latest_report = gh.read_latest_report()
            reports = [latest_report] if latest_report else []

            parsed_plan = parse_plan(plan_raw or default_plan(goal))

            ui.print_plan_status(render_plan(parsed_plan))

            steps = parsed_plan["steps"]
            next_step = find_next_step(steps)

            # All done?
            if not next_step:
                ui.print_mission_done()
                parsed_plan["meta"]["STATE"] = "DONE"
                gh.put_file(PLAN_PATH, render_plan(parsed_plan), "Supervisor: mission completed")
                gh.put_file(TASK_MOTHER_PATH, "DONE", "Supervisor: done")
                time.sleep(POLL_SECONDS)
                continue

            # Judge latest report
            latest_name = latest_report[0] if latest_report else None
            latest_text = latest_report[1] if latest_report else ""

            if latest_name and latest_name != state.get("last_report_name_seen"):
                target = next_step
                if target["STATUS"].upper() == "IN_PROGRESS":
                    judge = supervisor.judge_step(
                        parsed_plan["meta"].get("GOAL", goal), target, latest_text
                    )
                    if judge["verdict"] == "PASS":
                        target["STATUS"] = "DONE"
                        parsed_plan["notes"].append(
                            f"STEP {target['id']} PASS: {judge['reason']}"
                        )
                        ui.step_progress(
                            target["id"], target["TITLE"], "DONE", "PASS", judge["reason"]
                        )
                    else:
                        target["STATUS"] = "RETRY"
                        target["RETRIES"] = int(target.get("RETRIES", 0)) + 1
                        parsed_plan["notes"].append(
                            f"STEP {target['id']} FAIL: {judge['reason']}"
                        )
                        ui.step_progress(
                            target["id"], target["TITLE"], "RETRY", "FAIL", judge["reason"]
                        )
                        if target["RETRIES"] > MAX_RETRIES_PER_STEP:
                            parsed_plan["meta"]["STATE"] = "FAILED"
                            gh.put_file(
                                TASK_MOTHER_PATH, "FAILED", "Supervisor: max retries reached"
                            )

                    gh.put_file(
                        PLAN_PATH, render_plan(parsed_plan), "Supervisor: update plan from report"
                    )
                state["last_report_name_seen"] = latest_name
                state_mgr.save(state)

            # Reload plan after evaluation
            plan_raw, _ = gh.get_file(PLAN_PATH)
            parsed_plan = parse_plan(plan_raw or default_plan(goal))
            steps = parsed_plan["steps"]
            next_step = find_next_step(steps)

            if not next_step:
                time.sleep(POLL_SECONDS)
                continue

            # --- Dispatch new task ----------------------------------------
            tasks_raw, _ = gh.get_file(TASKS_PATH)
            if (tasks_raw or "").strip().lower() in ("waiting for tasks", "", "done"):
                refined = supervisor.generate_or_refine_plan(
                    parsed_plan["meta"].get("GOAL", goal), plan_raw or "", reports
                )
                if refined and "# MISSION PLAN" in refined:
                    parsed_plan = parse_plan(refined)
                    gh.put_file(
                        PLAN_PATH, render_plan(parsed_plan), "Supervisor: refine plan"
                    )
                    steps = parsed_plan["steps"]
                    next_step = find_next_step(steps)
                    if not next_step:
                        time.sleep(POLL_SECONDS)
                        continue

                action = supervisor.build_execution(
                    parsed_plan["meta"].get("GOAL", goal), next_step, reports
                )
                payload = build_task_payload(
                    step_id=next_step["id"],
                    engine=action["ENGINE"],
                    mode=action["MODE"],
                    content=action["CONTENT"],
                )

                ui.print_dispatched_task(next_step["id"], payload)

                ok = gh.put_file(
                    TASKS_PATH, payload, f"Supervisor: dispatch STEP {next_step['id']}"
                )
                if ok:
                    for s in parsed_plan["steps"]:
                        if s["id"] == next_step["id"]:
                            s["STATUS"] = "IN_PROGRESS"
                            s["ENGINE"] = action["ENGINE"]
                    gh.put_file(
                        PLAN_PATH,
                        render_plan(parsed_plan),
                        f"Supervisor: STEP {next_step['id']} IN_PROGRESS",
                    )
                    state["last_task_id_sent"] = next_step["id"]
                    state_mgr.save(state)

            time.sleep(POLL_SECONDS)

        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            if "429" in str(e):
                time.sleep(60)
            else:
                time.sleep(10)

    # --- Clean exit --------------------------------------------------------
    print("\n\u2705 [SHUTDOWN] Agent stopped cleanly.")
    logger.info("Agent stopped by signal.")


if __name__ == "__main__":
    main()
