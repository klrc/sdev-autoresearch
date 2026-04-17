#!/usr/bin/env python3
"""CLI entry point for sdev.

Usage::

    sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200
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

    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser(
        "set-default",
        help="Persist device/baud as the default for future invocations.",
    )

    args = parser.parse_args()

    # --- set-default subcommand ---
    if args.subcommand == "set-default":
        if args.device is None or args.baud is None:
            parser.error("set-default requires -d DEVICE and -b BAUD")
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

    result = sdev.run(device, baud, args.command)

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
