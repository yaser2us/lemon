"""Run with python3 -m lemon. Custom scenarios, Anthropic review and compare make API calls."""

import argparse
import json
import math
import shlex
import sys
from pathlib import Path

from .contracts import definitions
from .chat import ChatViewer, load_chat
from .anthropic_reviewer import AnthropicClient, AnthropicReviewer, ReviewError, load_configuration
from .design import DesignWorld, VARIANTS
from .discussion import run_discussion, save_discussion, validate_discussion, approve_proposal
from .proposal import shared_proposal
from .design_evaluation import evaluate_design
from .design_reporting import render_design, save_comparison, save_design, save_design_index
from .evaluation import evaluate
from .events import replay
from .reporting import render_report, save_run, save_suite
from .runtime import World
from .scenarios import SCENARIOS, get_scenario
from .actor_world import FAULTS, ModelActor, run_actor, save_actor


def run_scenario(name, seed):
    scenario = get_scenario(name)
    run = World(scenario["config"], seed).run()
    run["description"] = scenario["description"]
    run["expectations"] = scenario["expected"]
    run["quality"] = evaluate(run, scenario["expected"])
    return run


def run_design(variant, seed, reviewer=None, on_event=None):
    run = DesignWorld(seed=seed, variant=variant, reviewer=reviewer, on_event=on_event).run()
    run["quality"] = evaluate_design(run)
    return run


def configured_reviewer(args):
    key, model = load_configuration(args.env_file)
    return AnthropicReviewer(AnthropicClient(key, model, timeout=args.api_timeout, max_requests=args.max_api_requests))


def read_feedback(viewer, run):
    viewer.note("Your turn. Enter feedback, /changes, /proposal, /versions, /approve REVISION, /questions, or /quit.")
    while True:
        try:
            answer = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            viewer.note("Conversation saved. Resume it whenever you are ready.")
            return None
        if answer == "/quit":
            return None
        if answer == "/proposal":
            viewer.proposal(run)
            continue
        if answer == "/versions":
            viewer.versions(run)
            continue
        if answer == "/changes":
            viewer.changes(run)
            continue
        if answer.lower().rstrip(".! ") == "approve this proposal":
            return {"approve_revision": shared_proposal(run["final_state"])["revision"]}
        if answer.startswith("/approve"):
            parts = answer.split()
            if len(parts) == 2 and parts[0] == "/approve" and parts[1].isdigit():
                return {"approve_revision": int(parts[1])}
            viewer.note("Use /approve {} to approve the displayed revision.".format(shared_proposal(run["final_state"])["revision"]))
            continue
        if answer == "/questions":
            for question in run["final_state"]["questions"]:
                viewer.note(question)
            if not run["final_state"]["questions"]:
                viewer.note("No open questions. You can still add a constraint or challenge a proposal.")
            continue
        if answer.startswith("/"):
            viewer.note("Commands: /changes, /proposal, /versions, /approve REVISION, /questions, /quit.")
            continue
        if not 1 <= len(answer) <= 12000:
            viewer.note("Enter 1-12000 characters, or /quit.")
            continue
        return answer


def scenario_chat(args, viewer):
    def save_checkpoint(run):
        raw, report = save_discussion(run, args.output)
        viewer.note("Saved conversation: {}".format(report))
        viewer.note("Shared proposal: {}".format(raw.with_suffix(".proposal.md")))
        viewer.note("Change review: {}".format(raw.with_suffix(".changes.md")))
        viewer.write("Replay: python3 -m lemon chat {}".format(shlex.quote(str(raw))))
        viewer.write("Continue: python3 -m lemon chat --resume {}".format(shlex.quote(str(raw))))
        viewer.finish(run)

    def feedback_or_approval(run):
        while True:
            answer = read_feedback(viewer, run)
            if not isinstance(answer, dict):
                return run, answer
            try:
                run = approve_proposal(run, answer["approve_revision"])
            except ValueError as exc:
                viewer.note(str(exc))
                continue
            save_checkpoint(run)
            viewer.note("Approval saved. Further feedback creates a new draft.")

    previous = load_chat(args.resume) if args.resume else None
    if previous:
        validate_discussion(previous)
        scenario = previous["final_state"]["scenario"]
    else:
        scenario = args.scenario_file.read_text(encoding="utf-8") if args.scenario_file else args.scenario
    if not isinstance(scenario, str) or not 1 <= len(scenario.strip()) <= 12000:
        raise ValueError("Scenario must contain 1-12000 characters")
    interactive = args.interactive or (args.resume is not None and args.message is None and args.reviewer_feedback is None)
    rounds = args.rounds if args.rounds is not None else (1 if interactive or args.resume else 2)
    viewer.start(live=True)
    viewer.note("Scenario: " + scenario)
    viewer.note("All four roles use Anthropic. Budget: {} HTTP attempts for this invocation; {} round(s) per reply.".format(args.max_api_requests, rounds))
    feedback = args.message
    if previous:
        viewer.finish(previous)
        if args.approve_revision is not None:
            approved = approve_proposal(previous, args.approve_revision)
            save_checkpoint(approved)
            return approved
        if feedback is None and args.reviewer_feedback is None:
            previous, feedback = feedback_or_approval(previous)
            if feedback is None:
                return previous
    key, model = load_configuration(args.env_file)
    client = AnthropicClient(key, model, timeout=args.api_timeout, max_requests=args.max_api_requests)
    while True:
        run = run_discussion(scenario, client, rounds=rounds, on_event=viewer.event, previous=previous, user_message=feedback,
                             reviewer_feedback=args.reviewer_feedback)
        args.reviewer_feedback = None
        save_checkpoint(run)
        if not interactive or run["final_state"]["status"] in {"needs_review", "paused"}:
            return run
        if client.requests >= client.max_requests:
            viewer.note("This invocation's API budget is used. Your conversation is saved; use --resume to continue.")
            return run
        viewer.note("{} HTTP attempts remaining.".format(client.max_requests - client.requests))
        run, feedback = feedback_or_approval(run)
        if feedback is None:
            return run
        previous = run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lemon agent communication simulator (Python 3.9+, no dependencies)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List scenario descriptions")
    commands.add_parser("contracts", help="Print versioned participants, capabilities and laws")
    run_parser = commands.add_parser("run", help="Run one scenario and save its conversation")
    run_parser.add_argument("scenario", choices=list(SCENARIOS))
    run_parser.add_argument("--seed", type=int, default=7)
    run_parser.add_argument("--output", type=Path, default=Path("runs/review"))
    run_parser.add_argument("--show", action="store_true", help="Also print the readable conversation report")
    suite_parser = commands.add_parser("suite", help="Run all scenarios and generate a review index")
    suite_parser.add_argument("--seed", type=int, default=7, help="First scheduler seed")
    suite_parser.add_argument("--seeds", type=int, default=1, help="Number of consecutive seeds")
    suite_parser.add_argument("--output", type=Path, default=Path("runs/review"))
    replay_parser = commands.add_parser("replay", help="Verify a saved event log and reconstruct state without execution")
    replay_parser.add_argument("run", type=Path)
    design_parser = commands.add_parser("design", help="Negotiate a software interface with Product, Backend, UI and Test agents")
    design_parser.add_argument("--variant", choices=list(VARIANTS) + ["all"], default="negotiated")
    design_parser.add_argument("--seed", type=int, default=7)
    design_parser.add_argument("--output", type=Path, default=Path("runs/design"))
    design_parser.add_argument("--show", action="store_true", help="Print the recorded design conversation")
    design_parser.add_argument("--reviewer", choices=["deterministic", "anthropic"], default="deterministic", help="Anthropic enables paid API calls for the Test Agent")
    compare_parser = commands.add_parser("compare", help="Run a deterministic baseline and one live Anthropic Test Agent under the same scenario")
    compare_parser.add_argument("--variant", choices=list(VARIANTS), default="negotiated")
    compare_parser.add_argument("--seed", type=int, default=7)
    compare_parser.add_argument("--output", type=Path, default=Path("runs/comparison"))
    chat_parser = commands.add_parser("chat", help="Watch agent chats live, or replay a saved JSON conversation")
    chat_parser.add_argument("file", nargs="?", type=Path, help="Saved run to verify and play without API calls")
    chat_parser.add_argument("--reviewer", choices=["deterministic", "anthropic"], default="deterministic", help="Live Test Agent provider; Anthropic makes paid API calls")
    chat_parser.add_argument("--variant", choices=list(VARIANTS), default="negotiated")
    chat_parser.add_argument("--seed", type=int, default=7)
    chat_parser.add_argument("--output", type=Path, default=Path("runs/chat"))
    chat_parser.add_argument("--delay", type=float, help="Seconds between chat cards (default: 0.45 in terminal, 0 when piped)")
    chat_parser.add_argument("--details", action="store_true", help="Show full message payloads, including proposed tests")
    chat_parser.add_argument("--no-color", action="store_true")
    scenario_source = chat_parser.add_mutually_exclusive_group()
    scenario_source.add_argument("--scenario", help="Discuss your own scenario with four Anthropic roles (paid API calls)")
    scenario_source.add_argument("--scenario-file", type=Path, help="Read a custom scenario from a UTF-8 text file (paid API calls)")
    scenario_source.add_argument("--resume", type=Path, help="Continue a saved scenario discussion with your feedback (paid API calls)")
    chat_parser.add_argument("--interactive", action="store_true", help="Take turns with the agents in a custom scenario discussion")
    chat_parser.add_argument("--message", help="Feedback for --resume, without an interactive prompt")
    chat_parser.add_argument("--reviewer-feedback", help="Technical reviewer critique, recorded separately from user decisions")
    chat_parser.add_argument("--approve-revision", type=int, help="Approve this revision of --resume locally, with no API calls")
    chat_parser.add_argument("--rounds", type=int, help="Rounds per discussion batch, 1-5 (default 1 interactive/resume, otherwise 2)")
    actor_parser = commands.add_parser("act", help="Enact a fictional transfer, explore branches, and retain a tested recovery strategy")
    actor_parser.add_argument("--fault", choices=FAULTS, default="response-lost")
    actor_parser.add_argument("--agent", choices=["local", "anthropic"], default="local", help="App actor implementation; Anthropic makes paid API calls")
    actor_parser.add_argument("--output", type=Path, default=Path("runs/actors"))
    actor_parser.add_argument("--memory", type=Path, default=Path("runs/actors/strategy.json"))
    actor_parser.add_argument("--fresh", action="store_true", help="Explore without reading existing strategy memory; still save a newly learned strategy")
    actor_parser.add_argument("--delay", type=float, default=0, help="Chat playback delay in seconds")
    for provider_parser in (design_parser, compare_parser, chat_parser, actor_parser):
        provider_parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
        provider_parser.add_argument("--api-timeout", type=float, default=30, help="Per-request socket timeout in seconds (maximum 60)")
        provider_parser.add_argument("--max-api-requests", type=int, default=8, help="Maximum HTTP attempts per conversation, including retries")
    args = parser.parse_args(argv)
    try:
        if args.command == "act":
            if not math.isfinite(args.delay) or args.delay < 0:
                parser.error("--delay must be finite and nonnegative")
            memory = json.loads(args.memory.read_text(encoding="utf-8")) if not args.fresh and args.memory.exists() else None
            actor = None
            if args.agent == "anthropic":
                key, model = load_configuration(args.env_file)
                actor = ModelActor(AnthropicClient(key, model, timeout=args.api_timeout, max_requests=args.max_api_requests))
            viewer = ChatViewer(delay=args.delay)
            viewer.start(live=True)
            viewer.note("Actor simulation / App: {} / bank roles follow declared local model rules / no real payment".format(args.agent))
            run = run_actor(args.fault, actor=actor, memory=memory, on_event=viewer.event)
            path = save_actor(run, args.output, args.memory)
            viewer.finish(run)
            viewer.write("Saved actor trace and branch experiments: {}".format(path))
            if run["learned_strategy"]:
                viewer.write("Retained strategy: {}".format(args.memory))
            return 0 if run["quality"]["passed"] else 1
        elif args.command == "chat":
            custom = args.scenario is not None or args.scenario_file is not None or args.resume is not None
            if args.reviewer_feedback is not None and (not custom or not 1 <= len(args.reviewer_feedback.strip()) <= 12000):
                parser.error("--reviewer-feedback requires a custom scenario or resume and 1-12000 characters")
            if args.approve_revision is not None and (not args.resume or args.message is not None or args.reviewer_feedback is not None):
                parser.error("--approve-revision requires --resume and cannot be combined with --message")
            if args.interactive and not custom:
                parser.error("--interactive requires --scenario, --scenario-file or --resume")
            if args.message is not None and (not args.resume or not 1 <= len(args.message.strip()) <= 12000):
                parser.error("--message requires --resume and 1-12000 characters of feedback")
            if custom and (args.file or args.variant != "negotiated"):
                parser.error("Use a custom scenario on its own, without a replay file or transfer variant")
            if args.rounds is not None and not 1 <= args.rounds <= 5:
                parser.error("--rounds must be between 1 and 5")
            if args.delay is not None and (not math.isfinite(args.delay) or args.delay < 0):
                parser.error("--delay must be a finite nonnegative number")
            if args.file and args.reviewer != "deterministic":
                parser.error("Saved chats never call a reviewer; omit --reviewer")
            viewer = ChatViewer(delay=args.delay, details=args.details, no_color=args.no_color)
            if custom:
                run = scenario_chat(args, viewer)
            elif args.file:
                run = load_chat(args.file)
                viewer.start(live=False)
                for event in run["events"]:
                    viewer.event(event)
            else:
                reviewer = configured_reviewer(args) if args.reviewer == "anthropic" else None
                viewer.start(live=True)
                run = run_design(args.variant, args.seed, reviewer=reviewer, on_event=viewer.event)
                report = save_design(run, args.output)
                viewer.note("Saved conversation: {}".format(report))
            if not custom:
                viewer.finish(run)
            if run.get("domain") == "scenario-discussion":
                if run["final_state"]["status"] == "paused":
                    return 130
                return 1 if run["final_state"]["status"] == "needs_review" else 0
            return 0 if run.get("quality", {}).get("passed", True) else 1
        elif args.command == "list":
            for name, scenario in SCENARIOS.items():
                print("{:<24} {}".format(name, scenario["description"]))
        elif args.command == "contracts":
            print(json.dumps(definitions(), indent=2, sort_keys=True))
        elif args.command == "run":
            run = run_scenario(args.scenario, args.seed)
            raw, report = save_run(run, args.output)
            if args.show:
                print(render_report(run))
            print("{}: {}\nConversation: {}\nReplay data: {}".format(args.scenario, "PASS" if run["quality"]["passed"] else "FAIL", report, raw))
            return 0 if run["quality"]["passed"] else 1
        elif args.command == "design":
            runs = []
            for variant in VARIANTS if args.variant == "all" else [args.variant]:
                reviewer = configured_reviewer(args) if args.reviewer == "anthropic" else None
                run = run_design(variant, args.seed, reviewer=reviewer)
                report = save_design(run, args.output)
                runs.append(run)
                if args.show:
                    print(render_design(run))
                print("{}: {} (checks {})\nConversation: {}".format(variant, run["final_state"]["status"], "PASS" if run["quality"]["passed"] else "FAIL", report))
            if args.variant == "all":
                print("Review: {}".format(save_design_index(runs, args.output)))
            return 0 if all(run["quality"]["passed"] for run in runs) else 1
        elif args.command == "compare":
            reviewer = configured_reviewer(args)
            baseline = run_design(args.variant, args.seed)
            candidate = run_design(args.variant, args.seed, reviewer=reviewer)
            report = save_comparison(baseline, candidate, args.output)
            print("Baseline: {}\nAnthropic: {}\nComparison: {}".format(baseline["final_state"]["status"], candidate["final_state"]["status"], report))
            if not candidate["quality"]["passed"]:
                print("Anthropic checks failed; reason: {}. Inspect the saved report.".format(candidate["final_state"]["reason"]))
            return 0 if baseline["quality"]["passed"] and candidate["quality"]["passed"] else 1
        elif args.command == "suite":
            if args.seeds < 1:
                parser.error("--seeds must be positive")
            runs = []
            for seed in range(args.seed, args.seed + args.seeds):
                for name in SCENARIOS:
                    run = run_scenario(name, seed)
                    save_run(run, args.output)
                    runs.append(run)
                    print("{} seed={} {}".format(name, seed, "PASS" if run["quality"]["passed"] else "FAIL"))
            index = save_suite(runs, args.output)
            passed = sum(run["quality"]["passed"] for run in runs)
            print("\n{} / {} passed. Review: {}".format(passed, len(runs), index))
            return 0 if passed == len(runs) else 1
        elif args.command == "replay":
            run = json.loads(args.run.read_text(encoding="utf-8"))
            if run.get("format_version") != 1:
                raise ValueError("Unsupported run format")
            state = replay(run["events"])
            if state != run["final_state"]:
                raise ValueError("Recorded final state differs from replay")
            print(json.dumps({"verified": True, "final_state": state}, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print("\nChat stopped. An interrupted live run is not saved.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except ReviewError as exc:
        print("Anthropic setup failed: {}. Check ANTHROPIC_API_KEY and ANTHROPIC_MODEL in the selected env file or environment.".format(exc.code), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
