from __future__ import annotations

import argparse
from typing import Sequence

from .config import load_config, validate_config
from .scheduler import run_scheduler
from .summary import generate_summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nga-summary", description="Generate NGA hot-topic summaries.")
    parser.add_argument("--config", help="Path to config file. Defaults to config.local.toml, then config.toml.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check-config", help="Validate config without printing secrets.")
    check_parser.add_argument("--no-llm", action="store_true", help="Do not require LLM settings.")

    run_parser = subparsers.add_parser("run", help="Run one crawl and summary generation.")
    run_parser.add_argument("--pages-per-forum", type=int, default=1, help="Forum pages to scan per target forum.")
    run_parser.add_argument("--no-llm", action="store_true", help="Write raw crawl digest instead of calling LLM.")

    schedule_parser = subparsers.add_parser("schedule", help="Run forever and generate summaries on schedule.")
    schedule_parser.add_argument("--pages-per-forum", type=int, default=1, help="Forum pages to scan per target forum.")
    schedule_parser.add_argument("--no-llm", action="store_true", help="Write raw crawl digest instead of calling LLM.")

    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001 - CLI should show actionable errors, not tracebacks.
        print(f"Failed to load config: {exc}", flush=True)
        return 1

    if args.command == "check-config":
        errors = validate_config(config, require_llm=not args.no_llm)
        if errors:
            print("Config check failed:", flush=True)
            for error in errors:
                print(f"- {error}", flush=True)
            return 1
        print("Config check passed.", flush=True)
        print(f"Config file: {config.path}", flush=True)
        print(f"Target forums: {', '.join(forum.name for forum in config.nga.target_forums)}", flush=True)
        print(f"LLM provider: {config.llm.provider}", flush=True)
        return 0

    require_llm = not args.no_llm
    errors = validate_config(config, require_llm=require_llm)
    if errors:
        print("Config check failed:", flush=True)
        for error in errors:
            print(f"- {error}", flush=True)
        return 1

    if args.command == "run":
        try:
            result = generate_summary(config, pages_per_forum=args.pages_per_forum, use_llm=not args.no_llm)
        except Exception as exc:  # noqa: BLE001 - keep CLI errors readable and secret-free.
            print(f"Run failed: {exc}", flush=True)
            return 1
        print(f"Summary written: {result.output_path}", flush=True)
        print(f"Threads listed: {result.fetched_threads}", flush=True)
        print(f"Threads fetched: {result.fetched_thread_contents}", flush=True)
        print(f"LLM used: {'yes' if result.used_llm else 'no'}", flush=True)
        return 0

    if args.command == "schedule":
        run_scheduler(config, pages_per_forum=args.pages_per_forum, use_llm=not args.no_llm)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
