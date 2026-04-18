#!/usr/bin/env python3
"""CLI entry point for sdev.

Usage::

    sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200
    sdev -p "tail -f /var/log/syslog" --stream -d /dev/ttyUSB0
    sdev -p "tail -f /var/log/syslog" --stream --grep "ERROR" -d /dev/ttyUSB0
    sdev -p "tail -f /var/log/syslog" --stream --line-mode -d /dev/ttyUSB0
    sdev -p "cat /proc/meminfo" --parse "Mem(Available|Total)" -d /dev/ttyUSB0
    sdev -p "./benchmark" --end-flag "Frame rate:" -d /dev/ttyUSB0
    sdev -p "uptime" --doctor -d /dev/ttyUSB0
    sdev -p "ls" --prompt "[root@board]# " -d /dev/ttyUSB0
    sdev set-default /dev/ttyUSB0 115200
    sdev -p "ls /proc/meminfo"          # uses saved defaults
    sdev --interrupt -d /dev/ttyUSB0    # send Ctrl+C without a command
"""

import argparse
import re
import sys

import sdev


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sdev",
        description="Run a command on a serial-attached Linux shell.",
    )
    parser.add_argument(
        "-p", "--command",
        help="Command to execute on the remote shell.",
    )
    parser.add_argument(
        "-d", "--device",
        help="Serial device path (default: saved default or /dev/ttyUSB0).",
    )
    parser.add_argument(
        "-b", "--baud",
        type=int,
        help="Baud rate (default: saved default or 115200).",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream output incrementally instead of buffering until prompt.",
    )
    parser.add_argument(
        "--parse",
        metavar="REGEX",
        help="Parse output and show only lines matching the regex.",
    )
    parser.add_argument(
        "--grep",
        metavar="REGEX",
        help="During --stream, only yield lines matching the regex.",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        help="Timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        dest="prompts",
        metavar="PATTERN",
        help="Shell prompt pattern(s) for completion detection (repeatable). "
             "Overrides default prompts like '# ', '$ ', etc.",
    )
    parser.add_argument(
        "--interrupt",
        action="store_true",
        help="Send Ctrl+C to interrupt a running command on the serial line "
             "and wait for the prompt. Use without -p.",
    )
    parser.add_argument(
        "--end-flag",
        metavar="MARKER",
        help="Stop waiting for output when this string appears (instead of shell prompt).",
    )
    parser.add_argument(
        "--line-mode",
        action="store_true",
        help="During --stream, yield complete lines only (buffer partial lines).",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Clear stray foreground processes and drain garbage before running a command.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Detect available serial boards on this system and print device info.",
    )
    parser.add_argument(
        "--probe-baud",
        type=int,
        default=None,
        action="append",
        dest="probe_bauds",
        help="Baud rates to try during --probe (repeatable, default: 115200).",
    )

    sub = parser.add_subparsers(dest="subcommand")
    set_parser = sub.add_parser(
        "set-default",
        help="Persist device/baud as the default for future invocations.",
    )
    set_parser.add_argument("device", help="Serial device path to save as default.")
    set_parser.add_argument("baud", type=int, help="Baud rate to save as default.")

    args = parser.parse_args()

    # Load saved defaults, then override with CLI flags
    defaults = sdev.load_defaults()

    # --- set-default subcommand ---
    if args.subcommand == "set-default":
        sdev.save_default(args.device, args.baud)
        print(f"Default saved: {args.device} @ {args.baud}")
        return

    # --- --interrupt: send Ctrl+C without running a command ---
    if args.interrupt:
        device = args.device or defaults.get("device", sdev.DEFAULT_DEVICE)
        baud = int(args.baud or defaults.get("baud", sdev.DEFAULT_BAUD))
        with sdev.SerialSession(device, baud) as sess:
            ok = sess.interrupt()
        if not ok:
            print("[sdev] interrupt: no prompt detected", file=sys.stderr)
            sys.exit(1)
        return

    # --- --probe: detect serial boards ---
    if args.probe:
        import json
        results = sdev.probe(baud_rates=args.probe_bauds, timeout=2)
        if not results:
            print("No serial devices detected.")
            sys.exit(1)
        for r in results:
            if "error" in r:
                print(f"{r['device']} @ {r['baud']}: ERROR: {r['error']}")
            else:
                info = r["info"]
                print(f"{r['device']} @ {r['baud']}: {info.get('os_name', '?')} / {info.get('hostname', '?')}")
        return

    # --- normal -p execution ---
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    device = args.device or defaults.get("device", sdev.DEFAULT_DEVICE)
    baud = args.baud or defaults.get("baud", sdev.DEFAULT_BAUD)

    # Convert prompt strings to bytes
    prompt_bytes = [p.encode() for p in args.prompts] if args.prompts else None

    with sdev.SerialSession(device, baud, prompts=prompt_bytes) as sess:
        if args.doctor:
            sess.doctor()

        if args.stream:
            if args.grep:
                _regex = re.compile(args.grep)

                def _grep_filter(text: str) -> str:
                    trailing_nl = text.endswith("\n")
                    lines = [l for l in text.splitlines() if _regex.search(l)]
                    result = "\n".join(lines)
                    if trailing_nl and result:
                        result += "\n"
                    return result

                filter_fn = _grep_filter
            else:
                filter_fn = None

            for chunk in sess.stream(
                args.command,
                timeout=args.timeout,
                filter_fn=filter_fn,
                line_mode=args.line_mode,
                end_flag=args.end_flag,
            ):
                sys.stdout.write(chunk)
            sys.stdout.flush()
        elif args.parse:
            result = sess.parse(args.command, pattern=args.parse, timeout=args.timeout)
            if result.matched:
                for line in result.matched:
                    print(line)
            else:
                print("(no matches)", file=sys.stderr)
                sys.exit(3)
        else:
            result = sess.cli(args.command, timeout=args.timeout, end_flag=args.end_flag)
            if result.output:
                sys.stdout.write(result.output)
            if result.timed_out:
                print(
                    f"\n[sdev] command timed out after {result.elapsed:.1f}s",
                    file=sys.stderr,
                )
                sys.exit(2)


if __name__ == "__main__":
    main()
