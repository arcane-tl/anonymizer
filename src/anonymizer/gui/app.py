"""Anonymizer options window — layout/copy parity with Mac droplet.

Thin wrapper: collects options, invokes anonymize CLI (or helper). Does not
reimplement detection. Target platform is Windows; tkinter also runs on macOS
for development.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as _tk_err:  # pragma: no cover - depends on OS Python build
    tk = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = _tk_err
else:
    _TK_IMPORT_ERROR = None

from anonymizer import __version__
from anonymizer.lists_io import load_lists, save_lists

MODE_LABELS = [
    ("strict", "Remove personal details (recommended)"),
    ("standard", "Remove identity only (keep company names)"),
    ("extract", "Convert to text only (no privacy scrub)"),
]
STYLE_LABELS = [
    ("placeholder", "Replace with tags  [PERSON_1]"),
    ("remove", "Delete text entirely (no tags)"),
]

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".text", ".markdown"}


def _find_anonymize() -> str | None:
    env = os.environ.get("ANONYMIZER_BIN")
    if env and Path(env).is_file():
        return env
    which = shutil.which("anonymize")
    if which:
        return which
    # Dev: project venv
    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path.cwd()):
        for rel in (
            ".venv/bin/anonymize",
            ".venv/Scripts/anonymize.exe",
            ".venv/Scripts/anonymize",
        ):
            cand = root / rel
            if cand.is_file():
                return str(cand)
    return None


def _lists_status(allow: str, deny: str) -> str:
    def count(text: str) -> int:
        n = 0
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                n += 1
        return n

    return (
        f"Allowlist {count(allow)}  ·  Denylist {count(deny)}  —  edit with Lists…"
    )


class ListsDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, allow: str, deny: str) -> None:
        super().__init__(master)
        self.title("Custom lists")
        self.resizable(True, True)
        self.result: tuple[str, str] | None = None
        self.transient(master)
        self.grab_set()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frm,
            text=(
                "One phrase per line. Allowlist is never redacted; "
                "denylist is always redacted. Done saves to "
                "~/.config/anonymizer/config.yaml."
            ),
            wraplength=420,
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frm, text="Allowlist — never redact", font=("", 11, "bold")).pack(
            anchor=tk.W
        )
        self.allow_txt = tk.Text(frm, height=8, width=52, font=("Segoe UI", 10))
        self.allow_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 12))
        self.allow_txt.insert("1.0", allow)

        ttk.Label(frm, text="Denylist — always redact", font=("", 11, "bold")).pack(
            anchor=tk.W
        )
        self.deny_txt = tk.Text(frm, height=8, width=52, font=("Segoe UI", 10))
        self.deny_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 12))
        self.deny_txt.insert("1.0", deny)

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side=tk.LEFT)
        ttk.Button(btns, text="Done", command=self._done).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

    def _done(self) -> None:
        self.result = (
            self.allow_txt.get("1.0", "end-1c"),
            self.deny_txt.get("1.0", "end-1c"),
        )
        try:
            save_lists(self.result[0], self.result[1])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Anonymizer", f"Could not save lists:\n{exc}", parent=self)
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class OptionsApp(tk.Tk):
    def __init__(self, files: list[Path]) -> None:
        super().__init__()
        self.files = [p.resolve() for p in files]
        self.title("")
        self.resizable(False, False)
        try:
            self.tk.call("tk", "scaling", 1.25)
        except tk.TclError:
            pass

        allow_lines, deny_lines = load_lists()
        self.allow_text = "\n".join(allow_lines)
        self.deny_text = "\n".join(deny_lines)

        self.mode_var = tk.StringVar(value="strict")
        self.style_var = tk.StringVar(value="placeholder")
        self.review_var = tk.BooleanVar(value=False)
        self.open_var = tk.BooleanVar(value=True)
        self.native_var = tk.BooleanVar(value=False)

        pad = 20
        root = ttk.Frame(self, padding=pad)
        root.pack(fill=tk.BOTH, expand=True)

        # Title
        title_row = ttk.Frame(root)
        title_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            title_row,
            text=f"Anonymizer (version {__version__})",
            font=("Segoe UI", 16, "bold"),
        ).pack(side=tk.LEFT)

        n = len(self.files)
        sub = (
            f"{n} document{'s' if n != 1 else ''} ready  ·  "
            "Saves next to original  ·  Private on this PC"
        )
        ttk.Label(root, text=sub, foreground="#555").pack(anchor=tk.W, pady=(0, 14))

        # Files
        ttk.Label(root, text="Files", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        files_box = tk.Text(root, height=5, width=56, font=("Segoe UI", 10), wrap=tk.WORD)
        files_box.pack(fill=tk.X, pady=(4, 14))
        files_box.insert("1.0", "\n".join(f"• {p.name}" for p in self.files))
        files_box.configure(state=tk.DISABLED)

        # Mode
        ttk.Label(root, text="Mode", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        for val, label in MODE_LABELS:
            ttk.Radiobutton(
                root, text=label, value=val, variable=self.mode_var
            ).pack(anchor=tk.W, pady=2)

        # Style
        ttk.Label(root, text="Output style", font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W, pady=(14, 0)
        )
        for val, label in STYLE_LABELS:
            ttk.Radiobutton(
                root, text=label, value=val, variable=self.style_var
            ).pack(anchor=tk.W, pady=2)

        # Lists
        ttk.Label(root, text="Custom lists", font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W, pady=(14, 0)
        )
        self.lists_lbl = ttk.Label(
            root, text=_lists_status(self.allow_text, self.deny_text), foreground="#666"
        )
        self.lists_lbl.pack(anchor=tk.W, pady=(4, 10))

        # Checks
        ttk.Checkbutton(
            root,
            text="Review findings before saving (opens Terminal)",
            variable=self.review_var,
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            root, text="Open result when finished", variable=self.open_var
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            root,
            text="Also save redacted original (PDF/DOCX)",
            variable=self.native_var,
        ).pack(anchor=tk.W, pady=2)

        # Actions
        bar = ttk.Frame(root)
        bar.pack(fill=tk.X, pady=(22, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side=tk.LEFT)
        right = ttk.Frame(bar)
        right.pack(side=tk.RIGHT)
        ttk.Button(right, text="Lists…", command=self._lists).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(right, text="Start", command=self._start).pack(side=tk.LEFT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._start())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _lists(self) -> None:
        dlg = ListsDialog(self, self.allow_text, self.deny_text)
        if dlg.result is not None:
            self.allow_text, self.deny_text = dlg.result
            self.lists_lbl.configure(
                text=_lists_status(self.allow_text, self.deny_text)
            )

    def _start(self) -> None:
        anon = _find_anonymize()
        if not anon:
            messagebox.showerror(
                "Anonymizer",
                "Could not find the anonymize CLI.\n"
                "Install it first (install.ps1 / brew / pip), then try again.",
                parent=self,
            )
            return

        mode = self.mode_var.get()
        style = self.style_var.get()
        want_review = self.review_var.get() and mode != "extract"
        want_open = self.open_var.get()
        want_native = self.native_var.get() and mode != "extract"

        # Temp list files
        allow_f = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        deny_f = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            allow_f.write(self.allow_text)
            deny_f.write(self.deny_text)
        finally:
            allow_f.close()
            deny_f.close()

        cfg_path = self._write_temp_config(style, allow_f.name, deny_f.name)
        common_flags = ["--config", str(cfg_path), "--redact-style", style]
        if want_native:
            common_flags.extend(["--format", "both"])

        if want_review:
            # One terminal session; process files sequentially
            cmds = [[anon, mode, str(p), *common_flags, "--review"] for p in self.files]
            self._run_review_batch(cmds, want_open, [allow_f.name, deny_f.name, str(cfg_path)])
            self.destroy()
            return

        self.withdraw()
        outputs: list[str] = []
        errors: list[str] = []
        try:
            for fpath in self.files:
                cmd = [anon, mode, str(fpath), *common_flags]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "error").strip()
                    errors.append(f"{fpath.name}: {err}")
                    continue
                outs = _parse_outputs(proc.stdout or "", proc.stderr or "")
                if not outs:
                    outs = _guess_outputs([fpath], mode, want_native)
                outputs.extend(outs)
        finally:
            for p in (allow_f.name, deny_f.name, str(cfg_path)):
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass

        if errors and not outputs:
            messagebox.showerror(
                "Anonymizer",
                "Something went wrong:\n\n" + "\n\n".join(errors[:3]),
            )
            self.deiconify()
            return

        if want_open and outputs:
            for out in outputs:
                try:
                    if sys.platform == "darwin":
                        subprocess.run(["open", out], check=False)
                    elif sys.platform == "win32":
                        os.startfile(out)  # type: ignore[attr-defined]
                    else:
                        subprocess.run(["xdg-open", out], check=False)
                except OSError:
                    pass
            self.destroy()
            return

        msg = "Done.\n\n"
        if outputs:
            msg += "Created:\n" + "\n".join(f"• {Path(o).name}" for o in outputs)
        else:
            msg += "Finished. Check next to your original files for .md / native output."
        if errors:
            msg += "\n\nSome files failed:\n" + "\n".join(errors[:5])
        if outputs and messagebox.askyesno(
            "Anonymizer", msg + "\n\nShow in folder?", parent=self
        ):
            folder = str(Path(outputs[0]).parent)
            if sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            elif sys.platform == "win32":
                subprocess.run(["explorer", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        else:
            messagebox.showinfo("Anonymizer", msg, parent=self)
        self.destroy()

    def _write_temp_config(self, style: str, allow_path: str, deny_path: str) -> Path:
        """Temp YAML config merging lists (same idea as Mac helper)."""
        import yaml

        cfg_path = Path(tempfile.mkstemp(suffix=".yaml", prefix="anonymizer-gui-")[1])
        allow_lines = [
            ln.strip()
            for ln in Path(allow_path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        deny_lines = [
            ln.strip()
            for ln in Path(deny_path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        data = {
            "redact_style": style,
            "allowlist": allow_lines,
            "denylist": [{"text": t, "entity_type": "ORG"} for t in deny_lines],
        }
        cfg_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return cfg_path

    def _run_review_batch(
        self, cmds: list[list[str]], want_open: bool, cleanup: list[str]
    ) -> None:
        messagebox.showinfo(
            "Anonymizer",
            "Complete the checklist in the terminal (space / enter).",
            parent=self,
        )
        env = os.environ.copy()
        if want_open:
            env["ANONYMIZER_OPEN"] = "1"
        # Sequential shell script in one terminal
        if sys.platform == "win32":
            parts = []
            for cmd in cmds:
                parts.append(subprocess.list2cmdline(cmd))
            parts.append("echo.")
            parts.append("echo --- Finished. You can close this window. ---")
            script = " & ".join(parts)
            if shutil.which("wt"):
                subprocess.Popen(
                    ["wt", "cmd", "/k", script],
                    env=env,
                )
            else:
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", script], env=env)
        elif sys.platform == "darwin":
            chain = " ; ".join(" ".join(shlex_quote(c) for c in cmd) for cmd in cmds)
            chain += '; echo; echo "--- Finished. You can close this window. ---"'
            # Escape for AppleScript double-quoted string
            chain_esc = chain.replace("\\", "\\\\").replace('"', '\\"')
            osa = f'tell application "Terminal" to do script "{chain_esc}"'
            subprocess.Popen(["osascript", "-e", osa], env=env)
        else:
            for cmd in cmds:
                subprocess.run(cmd, env=env)
        # Temp files cleaned by OS eventually; best-effort unlink after delay not needed


def shlex_quote(s: str) -> str:
    if sys.platform == "win32":
        return '"' + s.replace('"', '\\"') + '"'
    import shlex

    return shlex.quote(s)


def _parse_outputs(stdout: str, stderr: str) -> list[str]:
    out: list[str] = []
    for block in (stdout, stderr):
        for line in block.splitlines():
            if line.startswith("OUTPUT:"):
                p = line[7:].strip()
                if p:
                    out.append(p)
    return out


def _guess_outputs(files: list[Path], mode: str, native: bool) -> list[str]:
    paths: list[str] = []
    for f in files:
        if mode == "extract":
            cand = f.with_name(f"{f.stem}.md")
            if cand.resolve() == f.resolve():
                cand = f.with_name(f"{f.stem}.extracted.md")
        else:
            cand = f.with_name(f"{f.stem}.anonymized.md")
        if cand.is_file():
            paths.append(str(cand))
        if native and f.suffix.lower() in {".pdf", ".docx"}:
            n = f.with_name(f"{f.stem}.anonymized{f.suffix.lower()}")
            if n.is_file():
                paths.append(str(n))
    return paths


def _collect_files(argv: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in argv:
        p = Path(a).expanduser()
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> None:
    if tk is None:
        print(
            "error: tkinter is not available in this Python build.\n"
            "On Windows, install Python from python.org (includes Tcl/Tk).\n"
            f"Import error: {_TK_IMPORT_ERROR}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    args = list(sys.argv[1:] if argv is None else argv)
    files = _collect_files(args)
    # Hide root flash for file dialog
    root_probe = tk.Tk()
    root_probe.withdraw()
    if not files:
        paths = filedialog.askopenfilenames(
            title="Choose documents to anonymize",
            filetypes=[
                ("Documents", "*.pdf *.docx *.txt *.md"),
                ("All files", "*.*"),
            ],
        )
        files = [Path(p) for p in paths if Path(p).suffix.lower() in SUPPORTED]
    root_probe.destroy()
    if not files:
        return
    app = OptionsApp(files)
    app.mainloop()


if __name__ == "__main__":
    main()
