#!/usr/bin/env python3
"""Privacy scanner shared by the demo tooling (same patterns as .git/hooks/pre-commit).

Library:  from evidence_privacy import scan_text, scrub_text
CLI:      evidence_privacy.py [--tracked | FILE...]   exit 1 if anything is found.
The user/host names are computed at run time so this file never contains them.
"""
import getpass
import os
import re
import socket
import subprocess
import sys

USER = getpass.getuser()
HOST = socket.gethostname().split(".")[0]
HOME = os.path.expanduser("~")

_PATTERNS = [
    ("home path", r"/Users/[A-Za-z0-9._-]+"),
    ("linux home", r"/home/" + re.escape(USER)),
    ("user@", re.escape(USER) + "@"),
    ("personal email", r"[A-Za-z0-9._%+-]+@(gmail|yahoo|outlook|icloud|hotmail)\.com"),
    ("github token", r"gh[opsu]_[A-Za-z0-9]{20,}"),
    ("github pat", r"github_" + r"pat_"),
    ("aws key", r"AKIA[0-9A-Z]{16}"),
    ("private key", r"BEGIN [A-Z ]*PRIVATE KEY"),
    ("docker pat", r"dckr_" + r"pat_"),
    ("api key", r"sk-[A-Za-z0-9_-]{20,}"),
]
if HOST and len(HOST) > 2:
    _PATTERNS.append(("hostname", re.escape(HOST)))
if USER and len(USER) > 2:
    _PATTERNS.append(("username", r"\b" + re.escape(USER) + r"\b"))
_RX = [(n, re.compile(p)) for n, p in _PATTERNS]


def scan_text(text):
    """Return list of (line_no, kind, snippet-less) findings."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for name, rx in _RX:
            if rx.search(line):
                out.append((i, name))
    return out


def scrub_text(text):
    """Best-effort scrub of the home path (used on generated output, not as a substitute for the scan)."""
    if HOME and HOME != "/":
        text = text.replace(HOME, "~")
    return text


def _tracked(root):
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
    return [os.path.join(root, p) for p in r.stdout.decode().split("\0") if p]


def scan_file(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if b"\0" in data[:4096]:  # binary: scan raw bytes for the same strings
        t = data.decode("latin-1")
    else:
        t = data.decode("utf-8", "replace")
    return scan_text(t)


if __name__ == "__main__":
    args = sys.argv[1:]
    root = os.environ.get("LAB", os.path.join(HOME, "ai-chip-lab"))
    files = _tracked(root) if (not args or args == ["--tracked"]) else args
    bad = 0
    for p in files:
        for ln, kind in scan_file(p):
            print("%s:%d: %s" % (os.path.relpath(p, root) if p.startswith(root) else p, ln, kind))
            bad += 1
    print("privacy scan: %d finding(s) in %d file(s)" % (bad, len(files)))
    sys.exit(1 if bad else 0)
