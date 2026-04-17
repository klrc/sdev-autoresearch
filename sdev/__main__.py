#!/usr/bin/env python3
"""CLI entry point for sdev.

Usage::

    sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200
    sdev -p "tail -f /var/log/syslog" --stream -d /dev/ttyUSB0
    sdev -p "cat /proc/meminfo" --parse "Mem(Available|Total)" -d /dev/ttyUSB0
    sdev set-default /dev/ttyUSB0 115200
    sdev -p "ls /proc/meminfo"          # uses saved defaults
"""

import argparse
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
        "-t", "--timeout",
        type=float,
        help="Timeout in seconds (default: 300).",
    )

    sub = parser.add_subparsers(dest="subcommand")
    set_parser = sub.add_parser(
        "set-default",
        help="Persist device/baud as the default for future invocations.",
    )
    set_parser.add_argument("device", help="Serial device path to save as default.")
    set_parser.add_argument("baud", type=int, help="Baud rate to save as default.")

    args = parser.parse_args()

    # --- set-default subcommand ---
    if args.subcommand == "set-default":
        sdev.save_default(args.device, args.baud)
        print(f"Default saved: {args.device} @ {args.baud}")
        return

    # --- normal -p execution ---
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Load saved defaults, then override with CLI flags
    defaults = sdev.load_defaults()
    device = args.device or defaults.get("device", sdev.DEFAULT_DEVICE)
    baud = args.baud or defaults.get("baud", sdev.DEFAULT_BAUD)

    with sdev.SerialSession(device, baud) as sess:
        if args.stream:
            for chunk in sess.stream(args.command, timeout=args.timeout):
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
            result = sess.cli(args.command, timeout=args.timeout)
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
