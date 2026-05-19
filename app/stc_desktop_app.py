import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class STCDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Smart Trace Construction Prototype")
        self.geometry("980x680")
        self.minsize(820, 560)

        self.output_queue = queue.Queue()
        self.running = False

        self._build_ui()
        self.after(100, self._drain_output_queue)

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            root,
            text="Smart Trace Construction Prototype",
            font=("Segoe UI", 16, "bold"),
        )
        title.pack(anchor=tk.W)

        path_label = ttk.Label(root, text=f"Project root: {PROJECT_ROOT}")
        path_label.pack(anchor=tk.W, pady=(4, 12))

        button_frame = ttk.Frame(root)
        button_frame.pack(fill=tk.X, pady=(0, 12))

        self.run_buttons = []
        self._add_button(
            button_frame,
            "Run HDFS Pipeline",
            lambda: self._run_script("scripts/run_all_hdfs.ps1"),
        )
        self._add_button(
            button_frame,
            "Run BGL Pipeline",
            lambda: self._run_script("scripts/run_all_bgl.ps1"),
        )
        self._add_button(
            button_frame,
            "Run DBSCAN Extension",
            lambda: self._run_script("scripts/run_dbscan_extension.ps1"),
        )
        self._add_button(button_frame, "Open Outputs Folder", self._open_outputs)
        self._add_button(
            button_frame,
            "Open HDFS Summary",
            lambda: self._open_path("out/purity_table_with_baselines.csv"),
        )
        self._add_button(
            button_frame,
            "Open BGL Summary",
            lambda: self._open_path("out_bgl/summary_table_bgl.csv"),
        )

        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(root, textvariable=self.status_var)
        status_label.pack(anchor=tk.W, pady=(0, 6))

        self.output = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            font=("Consolas", 10),
            height=24,
        )
        self.output.pack(fill=tk.BOTH, expand=True)
        self.output.insert(tk.END, "Ready. Choose a pipeline to run.\n")
        self.output.configure(state=tk.DISABLED)

    def _add_button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
        if text.startswith("Run "):
            self.run_buttons.append(button)

    def _append_output(self, text):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _set_running(self, running):
        self.running = running
        state = tk.DISABLED if running else tk.NORMAL
        for button in self.run_buttons:
            button.configure(state=state)

    def _run_script(self, relative_script_path):
        if self.running:
            messagebox.showinfo("Pipeline Running", "A pipeline is already running.")
            return

        script_path = PROJECT_ROOT / relative_script_path
        if not script_path.exists():
            self._show_missing(f"Missing script: {script_path}")
            return

        command = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]

        self._set_running(True)
        self.status_var.set(f"Running {relative_script_path}")
        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output(f"Running: {' '.join(command)}\n\n")

        worker = threading.Thread(
            target=self._run_command_worker,
            args=(command, relative_script_path),
            daemon=True,
        )
        worker.start()

    def _run_command_worker(self, command, label):
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            if process.stdout is not None:
                for line in process.stdout:
                    self.output_queue.put(("output", line))

            return_code = process.wait()
            if return_code == 0:
                self.output_queue.put(("status", f"Finished {label}"))
                self.output_queue.put(("output", f"\nFinished with exit code 0.\n"))
            else:
                self.output_queue.put(("status", f"Failed {label}"))
                self.output_queue.put(
                    ("output", f"\nCommand failed with exit code {return_code}.\n")
                )
        except FileNotFoundError:
            self.output_queue.put(("status", "PowerShell not found"))
            self.output_queue.put(
                (
                    "output",
                    "\nError: PowerShell was not found. Run this app on Windows or install PowerShell.\n",
                )
            )
        except Exception as exc:
            self.output_queue.put(("status", "Command failed"))
            self.output_queue.put(("output", f"\nError: {exc}\n"))
        finally:
            self.output_queue.put(("done", None))

    def _drain_output_queue(self):
        try:
            while True:
                kind, value = self.output_queue.get_nowait()
                if kind == "output":
                    self._append_output(value)
                elif kind == "status":
                    self.status_var.set(value)
                elif kind == "done":
                    self._set_running(False)
        except queue.Empty:
            pass

        self.after(100, self._drain_output_queue)

    def _open_outputs(self):
        paths = [PROJECT_ROOT / "out", PROJECT_ROOT / "out_bgl"]
        existing = [path for path in paths if path.exists()]

        if not existing:
            self._show_missing("Neither out/ nor out_bgl/ exists yet. Run a pipeline first.")
            return

        for path in existing:
            os.startfile(path)
            self._append_output(f"Opened: {path}\n")

        missing = [path for path in paths if not path.exists()]
        for path in missing:
            self._append_output(f"Not found: {path}\n")

    def _open_path(self, relative_path):
        path = PROJECT_ROOT / relative_path
        if not path.exists():
            self._show_missing(f"Missing file: {path}")
            return

        os.startfile(path)
        self._append_output(f"Opened: {path}\n")

    def _show_missing(self, message):
        self.status_var.set("Missing file")
        self._append_output(f"\n{message}\n")
        messagebox.showerror("Missing File", message)


def main():
    app = STCDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
