import csv
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import customtkinter as ctk

    CTK_AVAILABLE = True
except ImportError:
    ctk = None
    CTK_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERIC_DELTA_SECONDS = 60
GENERIC_DELTA_OPTIONS = ["5 seconds", "10 seconds", "60 seconds"]
DEFAULT_GENERIC_MODE = "correlation_weak"
GENERIC_MODE_OPTIONS = ["Correlation-weak mode", "Attribute-based mode"]

GENERIC_RECONSTRUCTED = (
    PROJECT_ROOT / f"out_generic/eventlog_STC_generic_{DEFAULT_GENERIC_MODE}_delta{DEFAULT_GENERIC_DELTA_SECONDS}s.csv"
)
GENERIC_SUMMARY = PROJECT_ROOT / "out_generic/summary_table_generic.csv"
GENERIC_PM_RESULTS = PROJECT_ROOT / "out_generic/pm_quality_table_generic.csv"
HDFS_RECONSTRUCTED = PROJECT_ROOT / "out/eventlog_STC_v2_history_ip_delta5s.csv"
HDFS_SUMMARY = PROJECT_ROOT / "out/purity_table_with_baselines.csv"
HDFS_PM_RESULTS = PROJECT_ROOT / "out/pm_quality_table_inductive_rq2.csv"
BGL_RECONSTRUCTED = PROJECT_ROOT / "out_bgl/eventlog_STC_bgl_delta5s.csv"
BGL_SUMMARY = PROJECT_ROOT / "out_bgl/summary_table_bgl.csv"
BGL_PM_RESULTS = PROJECT_ROOT / "out_bgl/pm_quality_table_bgl.csv"
GENERIC_PROCESS_MODEL_CANDIDATES = [
    PROJECT_ROOT / "out_generic/process_model_generic_bpmn.png",
    PROJECT_ROOT / "out_generic/process_model_generic_bpmn.svg",
    PROJECT_ROOT / "out_generic/process_model_generic_petri.png",
    PROJECT_ROOT / "out_generic/process_model_generic_petri.svg",
]
PROCESS_MODEL_CANDIDATES = [
    PROJECT_ROOT / "out/process_model_STC_delta5_bpmn.png",
    PROJECT_ROOT / "out/process_model_STC_delta5_bpmn.svg",
    PROJECT_ROOT / "out/process_model_STC_delta5_petri.png",
    PROJECT_ROOT / "out/process_model_STC_delta5_petri.svg",
    PROJECT_ROOT / "out/process_model_STC_delta5.png",
    PROJECT_ROOT / "out/process_model_STC_delta5.svg",
]

UNSUPPORTED_REASON = "Processing failed because timestamps and messages could not be extracted reliably."
UNSUPPORTED_SUGGESTION = "Please select a log file with recognizable timestamps or provide a structured CSV input."

STATUS_COLORS = {
    "Pending": "#8a8f98",
    "Running": "#2563eb",
    "Completed": "#16a34a",
    "Failed": "#dc2626",
}


class STCDemoApp:
    def __init__(self):
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
            self._configure_ttk_style()

        self.root.title("Smart Trace Construction Prototype")
        self.root.geometry("1180x780")
        self.root.minsize(980, 680)

        self.output_queue = queue.Queue()
        self.running = False
        self.technical_log_visible = False
        self.current_run_kind = "generic"
        self.current_result_kind = "none"
        self.current_generic_reconstructed_path = GENERIC_RECONSTRUCTED
        self.current_generic_summary_path = GENERIC_SUMMARY
        self.current_generic_pm_path = GENERIC_PM_RESULTS

        self.selected_log_path = tk.StringVar(value="No file selected")
        self.generic_delta_var = tk.StringVar(value=f"{DEFAULT_GENERIC_DELTA_SECONDS} seconds")
        self.generic_mode_var = tk.StringVar(value=GENERIC_MODE_OPTIONS[0])
        self.final_status_var = tk.StringVar(value="Ready. Select a log file to begin.")
        self.progress_text_var = tk.StringVar(value="Progress: 0%")
        self.summary_values = {}
        self.summary_row_widgets = {}
        self.step_widgets = {}
        self.run_buttons = []
        self.button_states = {}

        self._build_ui()
        self._reset_steps()
        self._reset_summary()
        self._set_progress(0)
        self._refresh_output_buttons()
        self.root.after(100, self._process_output)

    def _configure_ttk_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Sidebar.TFrame", background="#eef2f7")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), background="#eef2f7")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), background="#eef2f7", foreground="#475569")
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", foreground="#64748b")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        if CTK_AVAILABLE:
            self.root.grid_columnconfigure(1, weight=1)
            self.root.grid_rowconfigure(0, weight=1)
            self.sidebar = ctk.CTkFrame(self.root, width=300, corner_radius=0, fg_color="#eef2f7")
            self.sidebar.grid(row=0, column=0, sticky="nsew")
            self.main = ctk.CTkScrollableFrame(self.root, fg_color="#f8fafc", corner_radius=0)
            self.main.grid(row=0, column=1, sticky="nsew")
        else:
            self.root.grid_columnconfigure(1, weight=1)
            self.root.grid_rowconfigure(0, weight=1)
            self.sidebar = ttk.Frame(self.root, width=300, style="Sidebar.TFrame", padding=18)
            self.sidebar.grid(row=0, column=0, sticky="nsew")
            self.main_container = ttk.Frame(self.root)
            self.main_container.grid(row=0, column=1, sticky="nsew")
            self.main_container.grid_columnconfigure(0, weight=1)
            self.main_container.grid_rowconfigure(0, weight=1)

            self.main_canvas = tk.Canvas(self.main_container, bg="#f8fafc", highlightthickness=0)
            self.main_scrollbar = ttk.Scrollbar(
                self.main_container,
                orient="vertical",
                command=self.main_canvas.yview,
            )
            self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)
            self.main_canvas.grid(row=0, column=0, sticky="nsew")
            self.main_scrollbar.grid(row=0, column=1, sticky="ns")

            self.main = ttk.Frame(self.main_canvas, padding=18)
            self.main_window = self.main_canvas.create_window((0, 0), window=self.main, anchor="nw")
            self.main.bind("<Configure>", self._on_main_configure)
            self.main_canvas.bind("<Configure>", self._on_canvas_configure)
            self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(5, weight=1)

        self._build_sidebar()
        self._build_main_area()

    def _on_main_configure(self, _event):
        if not hasattr(self, "main_canvas"):
            return
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if not hasattr(self, "main_canvas"):
            return
        self.main_canvas.itemconfigure(self.main_window, width=event.width)

    def _on_mousewheel(self, event):
        if hasattr(self, "main_canvas"):
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_sidebar(self):
        self._label(
            self.sidebar,
            "Smart Trace Construction",
            font=("Segoe UI", 22, "bold"),
            style="Title.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(22, 4))
        self._label(
            self.sidebar,
            "Software logs to process-mining-ready event logs",
            wraplength=250,
            style="Subtitle.TLabel",
            text_color="#475569",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(0, 22))

        self._button(self.sidebar, "Select Log File", self._select_log_file).pack(
            fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 10)
        )
        self._label(
            self.sidebar,
            textvariable=self.selected_log_path,
            wraplength=250,
            text_color="#334155",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(0, 18))

        self._label(
            self.sidebar,
            "Inactivity threshold",
            font=("Segoe UI", 12, "bold"),
            text_color="#0f172a",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(0, 8))
        self._delta_selector(self.sidebar).pack(fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 16))

        self._label(
            self.sidebar,
            "Reconstruction mode",
            font=("Segoe UI", 12, "bold"),
            text_color="#0f172a",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(0, 8))
        self._mode_selector(self.sidebar).pack(fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 10))

        self._label(
            self.sidebar,
            "Generic raw log mode tries to detect timestamps and messages automatically. "
            "If parsing is unreliable, the system stops and reports the format as unsupported.\n\n"
            "Correlation-weak mode ignores detected IDs during grouping. "
            "Attribute-based mode uses detected correlation attributes such as block ID, "
            "request ID, session ID, trace ID, or transaction ID when available.",
            wraplength=250,
            text_color="#475569",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(0, 16))

        generic_button = self._button(
            self.sidebar,
            "Run Generic STC Processing",
            self._run_generic_processing,
            emphasis=True,
        )
        generic_button.pack(fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 20))
        self.run_buttons.append(generic_button)

        self._label(
            self.sidebar,
            "Advanced thesis experiments",
            font=("Segoe UI", 13, "bold"),
            text_color="#0f172a",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18 if CTK_AVAILABLE else 0, pady=(10, 8))

        hdfs_button = self._button(
            self.sidebar,
            "Run HDFS Thesis Demo",
            lambda: self._run_powershell_demo("scripts/demo_hdfs.ps1", "HDFS thesis profile"),
        )
        hdfs_button.pack(fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 8))
        self.run_buttons.append(hdfs_button)

        bgl_button = self._button(
            self.sidebar,
            "Run BGL Thesis Demo",
            lambda: self._run_powershell_demo("scripts/demo_bgl.ps1", "BGL thesis profile"),
        )
        bgl_button.pack(fill="x", padx=18 if CTK_AVAILABLE else 0, pady=(0, 8))
        self.run_buttons.append(bgl_button)

    def _build_main_area(self):
        top = self._frame(self.main, fg_color="#f8fafc")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        top.grid_columnconfigure(0, weight=1)

        self._label(
            top,
            "Prototype Dashboard",
            font=("Segoe UI", 20, "bold"),
            text_color="#0f172a",
            style="Header.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self._label(
            top,
            textvariable=self.final_status_var,
            font=("Segoe UI", 12),
            text_color="#475569",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._build_status_cards()
        self._build_progress_panel()
        self._build_summary_panel()
        self._build_output_buttons()
        self._build_technical_log()

    def _build_status_cards(self):
        panel = self._frame(self.main, fg_color="#f8fafc")
        panel.grid(row=1, column=0, sticky="ew", padx=18, pady=8)
        for column in range(5):
            panel.grid_columnconfigure(column, weight=1)

        steps = [
            "Input selected",
            "Parsing",
            "STC reconstruction",
            "Result generation",
            "Optional visualization",
        ]
        for column, step in enumerate(steps):
            card = self._frame(panel, fg_color="#ffffff", corner_radius=14)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            title = self._label(card, step, font=("Segoe UI", 11, "bold"), text_color="#0f172a")
            title.pack(anchor="w", padx=14, pady=(12, 4))
            status = self._label(card, "Pending", font=("Segoe UI", 12, "bold"), text_color=STATUS_COLORS["Pending"])
            status.pack(anchor="w", padx=14, pady=(0, 12))
            self.step_widgets[step] = status

    def _build_progress_panel(self):
        panel = self._frame(self.main, fg_color="#ffffff", corner_radius=14)
        panel.grid(row=2, column=0, sticky="ew", padx=18, pady=8)
        panel.grid_columnconfigure(0, weight=1)

        self._label(
            panel,
            textvariable=self.progress_text_var,
            font=("Segoe UI", 12, "bold"),
            text_color="#0f172a",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        if CTK_AVAILABLE:
            self.progress_bar = ctk.CTkProgressBar(panel, height=14, mode="determinate")
            self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
            self.progress_bar.set(0)
        else:
            self.progress_bar = ttk.Progressbar(panel, mode="determinate", maximum=100)
            self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
            self.progress_bar["value"] = 0

    def _build_summary_panel(self):
        panel = self._frame(self.main, fg_color="#ffffff", corner_radius=14)
        panel.grid(row=3, column=0, sticky="ew", padx=18, pady=8)
        panel.grid_columnconfigure(1, weight=1)

        self._label(panel, "Result summary", font=("Segoe UI", 15, "bold"), text_color="#0f172a").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8)
        )

        rows = [
            ("Input file", "input_file"),
            ("Reconstruction mode", "mode"),
            ("Inactivity threshold", "delta"),
            ("Parsed events", "parsed_events"),
            ("Parsing success rate", "success_rate"),
            ("Reconstructed cases", "cases"),
            ("Average trace length", "avg_trace_len"),
            ("Single-event trace percentage", "single_event_pct"),
            ("Oracle ID coverage", "oracle_coverage_pct"),
            ("Average purity", "avg_purity"),
            ("Median purity", "median_purity"),
            ("P90 purity", "p90_purity"),
            ("Mixed trace percentage", "mixed_trace_pct"),
            ("Reconstructed event log path", "reconstructed_path"),
            ("Summary table path", "summary_path"),
            ("Non-empty lines", "non_empty_lines"),
            ("Reason", "reason"),
            ("Suggestion", "suggestion"),
        ]

        for row, (label, key) in enumerate(rows, start=1):
            label_widget = self._label(panel, f"{label}:", text_color="#475569")
            label_widget.grid(row=row, column=0, sticky="nw", padx=16, pady=3)
            value = tk.StringVar(value="N/A")
            self.summary_values[key] = value
            value_widget = self._label(panel, textvariable=value, text_color="#0f172a", wraplength=720)
            value_widget.grid(row=row, column=1, sticky="w", padx=16, pady=3)
            self.summary_row_widgets[key] = (label_widget, value_widget)

    def _build_output_buttons(self):
        panel = self._frame(self.main, fg_color="#f8fafc")
        panel.grid(row=4, column=0, sticky="new", padx=18, pady=8)

        self.open_reconstructed_button = self._button(
            panel, "Open Reconstructed Event Log", self._open_reconstructed_event_log
        )
        self.open_reconstructed_button.grid(row=0, column=0, padx=(0, 12), pady=6, sticky="ew")

        self.open_summary_button = self._button(
            panel, "Open Summary Results", self._open_summary_results
        )
        self.open_summary_button.grid(row=0, column=1, padx=(0, 12), pady=6, sticky="ew")

        self.open_pm_button = self._button(panel, "Open Process Mining Results", self._open_process_mining_results)
        self.open_pm_button.grid(row=0, column=2, padx=(0, 12), pady=6, sticky="ew")

        self.open_visualization_button = self._button(panel, "Open Process Model Visualization", self._open_process_model)
        self.open_visualization_button.grid(row=1, column=0, padx=(0, 12), pady=6, sticky="ew")

        self.open_output_button = self._button(panel, "Open Output Folder", self._open_current_output_folder)
        self.open_output_button.grid(row=1, column=1, padx=(0, 12), pady=6, sticky="ew")

        self.toggle_log_button = self._button(panel, "Show / Hide Technical Log", self._toggle_technical_log)
        self.toggle_log_button.grid(row=1, column=2, padx=(0, 12), pady=6, sticky="ew")

        for column in range(3):
            panel.grid_columnconfigure(column, weight=1, minsize=230)

    def _build_technical_log(self):
        self.technical_panel = self._frame(self.main, fg_color="#ffffff", corner_radius=14)
        self.technical_panel.grid_columnconfigure(0, weight=1)
        self.technical_panel.grid_rowconfigure(1, weight=1)
        self._label(
            self.technical_panel,
            "Technical log",
            font=("Segoe UI", 14, "bold"),
            text_color="#0f172a",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        if CTK_AVAILABLE:
            self.output = ctk.CTkTextbox(self.technical_panel, height=160, font=("Consolas", 10))
            self.output.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        else:
            self.output = scrolledtext.ScrolledText(self.technical_panel, wrap=tk.WORD, font=("Consolas", 10), height=9)
            self.output.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self._append_output("Technical log ready. Raw command output will appear here.\n")

    def _frame(self, parent, fg_color=None, corner_radius=0):
        if CTK_AVAILABLE:
            return ctk.CTkFrame(parent, fg_color=fg_color, corner_radius=corner_radius)
        return ttk.Frame(parent, style="Card.TFrame" if fg_color == "#ffffff" else None, padding=10)

    def _label(self, parent, text=None, textvariable=None, font=None, text_color=None, wraplength=None, style=None):
        if CTK_AVAILABLE:
            return ctk.CTkLabel(
                parent,
                text=text if text is not None else "",
                textvariable=textvariable,
                font=font,
                text_color=text_color,
                wraplength=wraplength or 0,
                justify="left",
            )
        return ttk.Label(parent, text=text, textvariable=textvariable, font=font, wraplength=wraplength, style=style)

    def _button(self, parent, text, command, emphasis=False):
        if CTK_AVAILABLE:
            if emphasis:
                return ctk.CTkButton(
                    parent,
                    text=text,
                    command=command,
                    fg_color="#2563eb",
                    hover_color="#1d4ed8",
                    height=34,
                )
            return ctk.CTkButton(parent, text=text, command=command, height=34)
        return ttk.Button(parent, text=text, command=command, style="Accent.TButton" if emphasis else None)

    def _delta_selector(self, parent):
        if CTK_AVAILABLE and hasattr(ctk, "CTkSegmentedButton"):
            return ctk.CTkSegmentedButton(
                parent,
                values=GENERIC_DELTA_OPTIONS,
                variable=self.generic_delta_var,
                command=lambda _: self._on_delta_changed(),
            )
        if CTK_AVAILABLE:
            return ctk.CTkOptionMenu(
                parent,
                values=GENERIC_DELTA_OPTIONS,
                variable=self.generic_delta_var,
                command=lambda _: self._on_delta_changed(),
            )
        combo = ttk.Combobox(
            parent,
            textvariable=self.generic_delta_var,
            values=GENERIC_DELTA_OPTIONS,
            state="readonly",
        )
        combo.bind("<<ComboboxSelected>>", lambda _: self._on_delta_changed())
        return combo

    def _mode_selector(self, parent):
        if CTK_AVAILABLE:
            return ctk.CTkOptionMenu(
                parent,
                values=GENERIC_MODE_OPTIONS,
                variable=self.generic_mode_var,
                command=lambda _: self._on_generic_parameter_changed(),
            )
        combo = ttk.Combobox(
            parent,
            textvariable=self.generic_mode_var,
            values=GENERIC_MODE_OPTIONS,
            state="readonly",
        )
        combo.bind("<<ComboboxSelected>>", lambda _: self._on_generic_parameter_changed())
        return combo

    def _selected_generic_delta(self):
        match = re.match(r"(\d+)", self.generic_delta_var.get())
        return int(match.group(1)) if match else DEFAULT_GENERIC_DELTA_SECONDS

    def _selected_generic_mode(self):
        if self.generic_mode_var.get() == "Attribute-based mode":
            return "attribute_based"
        return "correlation_weak"

    def _generic_reconstructed_path(self):
        return (
            PROJECT_ROOT
            / f"out_generic/eventlog_STC_generic_{self._selected_generic_mode()}_delta{self._selected_generic_delta()}s.csv"
        )

    def _on_delta_changed(self):
        self._on_generic_parameter_changed()

    def _on_generic_parameter_changed(self):
        if self.running:
            return
        self.current_result_kind = "none"
        self.current_generic_reconstructed_path = self._generic_reconstructed_path()
        self._reset_steps()
        self._reset_summary()
        if self.selected_log_path.get() != "No file selected":
            self.summary_values["input_file"].set(self.selected_log_path.get())
            self._set_step("Input selected", "Completed")
        self.final_status_var.set("Generic STC parameter changed. Ready to run processing.")
        self._refresh_output_buttons()

    def _select_log_file(self):
        file_path = filedialog.askopenfilename(
            title="Select log file",
            initialdir=PROJECT_ROOT,
            filetypes=[
                ("Log and CSV files", "*.log *.csv *.txt"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            self.selected_log_path.set(file_path)
            self.current_result_kind = "none"
            self._reset_steps()
            self._reset_summary()
            self.summary_values["input_file"].set(file_path)
            self._set_step("Input selected", "Completed")
            self.final_status_var.set("Input selected. Ready to run generic STC processing.")
            self._refresh_output_buttons()

    def _append_output(self, text):
        if CTK_AVAILABLE:
            self.output.insert("end", text)
            self.output.see("end")
        else:
            self.output.configure(state=tk.NORMAL)
            self.output.insert(tk.END, text)
            self.output.see(tk.END)
            self.output.configure(state=tk.DISABLED)

    def _toggle_technical_log(self):
        if self.technical_log_visible:
            self.technical_panel.grid_forget()
            self.technical_log_visible = False
        else:
            self.technical_panel.grid(row=5, column=0, sticky="nsew", padx=18, pady=(8, 18))
            self.technical_log_visible = True
            self.root.after(100, self._scroll_main_to_bottom)

    def _scroll_main_to_bottom(self):
        try:
            if CTK_AVAILABLE and hasattr(self.main, "_parent_canvas"):
                self.main._parent_canvas.yview_moveto(1.0)
            elif hasattr(self, "main_canvas"):
                self.main_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _set_running(self, running):
        self.running = running
        state = "disabled" if running else "normal"
        for button in self.run_buttons:
            self._set_button_state(button, state)

    def _set_button_state(self, button, state):
        try:
            button_id = id(button)
            if self.button_states.get(button_id) == state:
                return
            current_state = button.cget("state")
            if current_state == state:
                self.button_states[button_id] = state
                return
            button.configure(state=state)
            self.button_states[button_id] = state
        except Exception:
            button.configure(state=state)

    def _reset_steps(self):
        for step in self.step_widgets:
            self._set_step(step, "Pending")
        if self.selected_log_path.get() != "No file selected":
            self._set_step("Input selected", "Completed")
        self._update_progress_from_steps()

    def _set_step(self, step, status):
        widget = self.step_widgets.get(step)
        if not widget:
            return
        color = STATUS_COLORS.get(status, STATUS_COLORS["Pending"])
        if CTK_AVAILABLE:
            widget.configure(text=status, text_color=color)
        else:
            widget.configure(text=status, foreground=color)
        self._update_progress_from_steps()

    def _set_progress(self, percent, text=None):
        percent = max(0, min(100, int(percent)))
        self.progress_text_var.set(text or f"Progress: {percent}%")
        if not hasattr(self, "progress_bar"):
            return
        if CTK_AVAILABLE:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(percent / 100)
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar["value"] = percent

    def _set_progress_running(self, percent, step_name):
        percent = max(0, min(99, int(percent)))
        self.progress_text_var.set(f"Progress: about {percent}% ({step_name} running)")
        if not hasattr(self, "progress_bar"):
            return
        if CTK_AVAILABLE:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(percent / 100)
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar["value"] = percent

    def _update_progress_from_steps(self):
        if not hasattr(self, "progress_bar"):
            return

        completed_values = {
            "Input selected": 10,
            "Parsing": 35,
            "STC reconstruction": 65,
            "Result generation": 90,
            "Optional visualization": 100,
        }
        running_values = {
            "Input selected": 5,
            "Parsing": 20,
            "STC reconstruction": 50,
            "Result generation": 78,
            "Optional visualization": 95,
        }

        progress = 0
        running_step = None
        failed_step = None
        for step in completed_values:
            status = self._get_step_text(step)
            if status == "Completed":
                progress = max(progress, completed_values[step])
            elif status == "Running":
                running_step = step
                progress = max(progress, running_values[step])
            elif status == "Failed":
                failed_step = step
                break

        if failed_step:
            self._set_progress(progress, f"Progress stopped at {progress}% ({failed_step} failed)")
        elif running_step:
            self._set_progress_running(progress, running_step)
        else:
            self._set_progress(progress)

    def _reset_summary(self):
        defaults = {
            "input_file": self.selected_log_path.get(),
            "mode": self._selected_generic_mode(),
            "delta": f"{self._selected_generic_delta()}s",
            "parsed_events": "N/A",
            "success_rate": "N/A",
            "cases": "N/A",
            "avg_trace_len": "N/A",
            "single_event_pct": "N/A",
            "oracle_coverage_pct": "N/A",
            "avg_purity": "N/A",
            "median_purity": "N/A",
            "p90_purity": "N/A",
            "mixed_trace_pct": "N/A",
            "reconstructed_path": str(self._generic_reconstructed_path().relative_to(PROJECT_ROOT)),
            "summary_path": str(GENERIC_SUMMARY.relative_to(PROJECT_ROOT)),
            "non_empty_lines": "N/A",
            "reason": "N/A",
            "suggestion": "N/A",
        }
        for key, value in defaults.items():
            self.summary_values[key].set(value)
        self._set_purity_rows_visible(False)

    def _set_purity_rows_visible(self, visible):
        purity_keys = [
            "oracle_coverage_pct",
            "avg_purity",
            "median_purity",
            "p90_purity",
            "mixed_trace_pct",
        ]
        for key in purity_keys:
            widgets = self.summary_row_widgets.get(key)
            if not widgets:
                continue
            for widget in widgets:
                if visible:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _run_generic_processing(self):
        if self.running:
            messagebox.showinfo("Processing Running", "STC processing is already running.")
            return

        selected = self.selected_log_path.get().strip()
        if not selected or selected == "No file selected":
            self._show_missing("Please select a raw log file first.")
            return

        log_path = Path(selected)
        if not log_path.exists():
            self._show_missing(f"Selected log file not found: {log_path}")
            return

        command = [
            sys.executable,
            "src/run_pipeline_generic.py",
            "--input",
            str(log_path),
            "--delta",
            str(self._selected_generic_delta()),
            "--mode",
            self._selected_generic_mode(),
        ]

        self.current_run_kind = "generic"
        self.current_result_kind = "none"
        self.current_generic_reconstructed_path = self._generic_reconstructed_path()
        self.current_generic_summary_path = GENERIC_SUMMARY
        self.current_generic_pm_path = GENERIC_PM_RESULTS
        self._reset_steps()
        self._reset_summary()
        self.summary_values["input_file"].set(str(log_path))
        self._set_step("Input selected", "Completed")
        self._set_step("Parsing", "Running")
        self.final_status_var.set("Generic STC processing is running.")
        self._refresh_output_buttons()

        self._set_running(True)
        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output("Generic raw log STC processing\n")
        self._append_output(f"Input log: {log_path}\n")
        self._append_output(f"Delta seconds: {self._selected_generic_delta()}\n\n")
        self._append_output(f"Reconstruction mode: {self._selected_generic_mode()}\n\n")

        thread = threading.Thread(target=self._run_commands_worker, args=([command], "generic"), daemon=True)
        thread.start()

    def _run_powershell_demo(self, relative_script, run_kind):
        if self.running:
            messagebox.showinfo("Processing Running", "STC processing is already running.")
            return

        script_path = PROJECT_ROOT / relative_script
        if not script_path.exists():
            self._show_missing(f"Missing script: {script_path}")
            return

        command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]

        self.current_run_kind = run_kind
        self.current_result_kind = "none"
        self._reset_steps()
        self._reset_summary()
        if run_kind == "HDFS thesis profile":
            self._set_thesis_summary_defaults(
                input_file="data/HDFS_v1/HDFS.log",
                reconstructed_path=HDFS_RECONSTRUCTED,
                summary_path=HDFS_SUMMARY,
            )
        elif run_kind == "BGL thesis profile":
            self._set_thesis_summary_defaults(
                input_file="data/BGL/BGL_2k.log",
                reconstructed_path=BGL_RECONSTRUCTED,
                summary_path=BGL_SUMMARY,
            )
        self._set_step("Input selected", "Completed")
        self._set_step("Parsing", "Running")
        self.final_status_var.set(f"{run_kind} is running.")
        self._refresh_output_buttons()

        self._set_running(True)
        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output(f"Running thesis demo: powershell -ExecutionPolicy Bypass -File .\\{relative_script}\n\n")

        thread = threading.Thread(target=self._run_commands_worker, args=([command], run_kind), daemon=True)
        thread.start()

    def _run_commands_worker(self, commands, run_kind):
        success = True
        try:
            for command in commands:
                display_command = " ".join(f'"{part}"' if " " in part else part for part in command)
                self.output_queue.put(("output", f"Running: {display_command}\n"))
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
                if return_code != 0:
                    success = False
                    self.output_queue.put(("output", f"\nCommand failed with exit code {return_code}.\n"))
                    break

                self.output_queue.put(("output", "\n"))
        except Exception as exc:
            success = False
            self.output_queue.put(("output", f"\nError: {exc}\n"))
        finally:
            self.output_queue.put(("finished", {"success": success, "run_kind": run_kind}))
            self.output_queue.put(("done", None))

    def _process_output(self):
        try:
            while True:
                kind, value = self.output_queue.get_nowait()
                if kind == "output":
                    self._append_output(value)
                    self._handle_output_line(value)
                elif kind == "finished":
                    self._handle_finished(value)
                elif kind == "done":
                    self._set_running(False)
                    self._refresh_output_buttons()
        except queue.Empty:
            pass

        self._refresh_output_buttons()
        self.root.after(100, self._process_output)

    def _handle_output_line(self, line):
        for raw_line in line.splitlines():
            text = raw_line.strip()
            if not text:
                continue

            self._handle_demo_step_line(text)

            match = re.match(r"Non-empty lines:\s*(.+)", text)
            if match:
                self.summary_values["non_empty_lines"].set(match.group(1))
                continue

            match = re.match(r"Parsed events:\s*(.+)", text)
            if match:
                self.summary_values["parsed_events"].set(match.group(1))
                continue

            match = re.match(r"Parsing success rate:\s*(.+)", text)
            if match:
                self.summary_values["success_rate"].set(match.group(1))
                continue

            match = re.match(r"Reconstruction mode:\s*(.+)", text)
            if match:
                self.summary_values["mode"].set(match.group(1))
                continue

            match = re.match(r"Delta seconds:\s*(.+)", text)
            if match:
                self.summary_values["delta"].set(f"{match.group(1)}s")
                continue

            if text.startswith("Saved prepared event log:"):
                self._set_step("Parsing", "Completed")
                self._set_step("STC reconstruction", "Running")
                continue

            if text.startswith("Saved reconstructed event log:"):
                self._set_step("STC reconstruction", "Completed")
                self._set_step("Result generation", "Running")
                path_text = text.split(":", 1)[1].strip()
                self.current_generic_reconstructed_path = self._resolve_output_path(path_text)
                self.summary_values["reconstructed_path"].set(path_text)
                continue

            if text.startswith("Saved generic summary table:"):
                self._set_step("Result generation", "Running")
                path_text = text.split(":", 1)[1].strip()
                self.current_generic_summary_path = self._resolve_output_path(path_text)
                self.summary_values["summary_path"].set(path_text)
                continue

            if text.startswith("Saved generic process mining table:"):
                path_text = text.split(":", 1)[1].strip()
                self.current_generic_pm_path = self._resolve_output_path(path_text)
                self._set_step("Result generation", "Completed")
                self._set_step("Optional visualization", "Running")
                continue

            if text.startswith("Saved generic process model visualization:"):
                self._set_step("Optional visualization", "Completed")
                continue

            if "Unsupported log format:" in text:
                self.summary_values["reason"].set("Processing failed because timestamps and messages could not be extracted reliably.")
                self.summary_values["suggestion"].set("Please select a log file with recognizable timestamps or provide a structured CSV input.")
                self._set_step("Parsing", "Failed")
                continue

            if "PermissionError" in text or "Permission denied" in text:
                self.summary_values["reason"].set(
                    "The output CSV could not be overwritten because Windows denied access to the file."
                )
                self.summary_values["suggestion"].set(
                    "Close any open result CSV files in Excel or another viewer, then run processing again."
                )

    def _handle_demo_step_line(self, text):
        if self.current_run_kind == "HDFS thesis profile":
            if text.startswith("Step 1:"):
                self._set_step("Parsing", "Running")
            elif text.startswith("Step 3:"):
                self._set_step("Parsing", "Completed")
                self._set_step("STC reconstruction", "Running")
            elif text.startswith("Step 7:"):
                self._set_step("STC reconstruction", "Completed")
                self._set_step("Result generation", "Running")
            elif text.startswith("Optional:"):
                self._set_step("Result generation", "Completed")
                self._set_step("Optional visualization", "Running")
            elif text.startswith("Final HDFS demo summary"):
                self._set_step("Optional visualization", "Completed")

            match = re.match(r"Events:\s*(\d+)", text)
            if match:
                self.summary_values["parsed_events"].set(match.group(1))

        elif self.current_run_kind == "BGL thesis profile":
            if text.startswith("Step 1:"):
                self._set_step("Parsing", "Running")
            elif text.startswith("Step 2:"):
                self._set_step("Parsing", "Completed")
                self._set_step("STC reconstruction", "Running")
            elif text.startswith("Step 3:"):
                self._set_step("STC reconstruction", "Completed")
                self._set_step("Result generation", "Running")
            elif text.startswith("Final BGL demo summary"):
                self._set_step("Result generation", "Completed")
                self._set_step("Optional visualization", "Pending")

    def _resolve_output_path(self, path_text):
        path = Path(path_text)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    def _handle_finished(self, result):
        success = result["success"]
        run_kind = result["run_kind"]

        if success:
            self.final_status_var.set("Processing completed successfully.")
            if run_kind == "generic":
                self.current_result_kind = "generic"
                self._set_step("Parsing", "Completed")
                self._set_step("STC reconstruction", "Completed")
                self._set_step("Result generation", "Completed")
                if any(path.exists() for path in GENERIC_PROCESS_MODEL_CANDIDATES):
                    self._set_step("Optional visualization", "Completed")
                else:
                    self._set_step("Optional visualization", "Pending")
                self._load_generic_summary_table()
                self._set_progress(100, "Progress: 100%")
            else:
                self.current_result_kind = run_kind
                self._set_step("Parsing", "Completed")
                self._set_step("STC reconstruction", "Completed")
                self._set_step("Result generation", "Completed")
                if run_kind == "HDFS thesis profile" and any(path.exists() for path in PROCESS_MODEL_CANDIDATES):
                    self._set_step("Optional visualization", "Completed")
                else:
                    self._set_step("Optional visualization", "Pending")
                self._load_thesis_summary_table(run_kind)
                self._set_progress(100, "Progress: 100%")
            return

        self.current_result_kind = "none"
        self.final_status_var.set("Processing failed. See summary below.")
        if run_kind == "generic":
            if self.summary_values["reason"].get() == "N/A":
                self.summary_values["reason"].set("Processing failed because timestamps and messages could not be extracted reliably.")
            if self.summary_values["suggestion"].get() == "N/A":
                self.summary_values["suggestion"].set("Please select a log file with recognizable timestamps or provide a structured CSV input.")
            for step in ["Parsing", "STC reconstruction", "Result generation"]:
                current = self._get_step_text(step)
                if current == "Running":
                    self._set_step(step, "Failed")
                    break
            reason = self.summary_values["reason"].get()
            suggestion = self.summary_values["suggestion"].get()
            messagebox.showerror(
                "Processing Failed",
                f"{reason}\n\n{suggestion}",
            )
        else:
            for step in ["Parsing", "STC reconstruction", "Result generation", "Optional visualization"]:
                if self._get_step_text(step) == "Running":
                    self._set_step(step, "Failed")
                    break

    def _get_step_text(self, step):
        widget = self.step_widgets[step]
        return widget.cget("text")

    def _load_generic_summary_table(self):
        if not self.current_generic_summary_path.exists():
            return
        try:
            with self.current_generic_summary_path.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle), None)
            if not row:
                return
            self.summary_values["cases"].set(row.get("cases", "N/A"))
            self.summary_values["mode"].set(row.get("mode", self._selected_generic_mode()))
            self.summary_values["delta"].set(f"{row.get('delta', self._selected_generic_delta())}s")
            self.summary_values["avg_trace_len"].set(row.get("avg_trace_len", "N/A"))
            self.summary_values["single_event_pct"].set(row.get("single_event_pct", "N/A"))
            self._load_purity_values(row)
            self.summary_values["reason"].set("N/A")
            self.summary_values["suggestion"].set("N/A")
        except Exception as exc:
            self._append_output(f"Could not read generic summary table: {exc}\n")

    def _load_purity_values(self, row):
        has_purity = bool(row.get("avg_purity"))
        if has_purity:
            self.summary_values["oracle_coverage_pct"].set(row.get("oracle_coverage_pct", "N/A"))
            self.summary_values["avg_purity"].set(row.get("avg_purity", "N/A"))
            self.summary_values["median_purity"].set(row.get("median_purity", "N/A"))
            self.summary_values["p90_purity"].set(row.get("p90_purity", "N/A"))
            self.summary_values["mixed_trace_pct"].set(row.get("mixed_trace_pct", "N/A"))
            self._set_purity_rows_visible(True)
        else:
            for key in ["oracle_coverage_pct", "avg_purity", "median_purity", "p90_purity", "mixed_trace_pct"]:
                self.summary_values[key].set("N/A")
            self._set_purity_rows_visible(False)

    def _set_thesis_summary_defaults(self, input_file, reconstructed_path, summary_path):
        self.summary_values["input_file"].set(input_file)
        self.summary_values["mode"].set("Thesis profile")
        self.summary_values["delta"].set("Fixed thesis setting")
        self.summary_values["parsed_events"].set("N/A")
        self.summary_values["success_rate"].set("N/A")
        self.summary_values["cases"].set("N/A")
        self.summary_values["avg_trace_len"].set("N/A")
        self.summary_values["single_event_pct"].set("N/A")
        self.summary_values["oracle_coverage_pct"].set("N/A")
        self.summary_values["avg_purity"].set("N/A")
        self.summary_values["median_purity"].set("N/A")
        self.summary_values["p90_purity"].set("N/A")
        self.summary_values["mixed_trace_pct"].set("N/A")
        self.summary_values["reconstructed_path"].set(str(reconstructed_path.relative_to(PROJECT_ROOT)))
        self.summary_values["summary_path"].set(str(summary_path.relative_to(PROJECT_ROOT)))
        self.summary_values["non_empty_lines"].set("N/A")
        self.summary_values["reason"].set("N/A")
        self.summary_values["suggestion"].set("N/A")

    def _load_thesis_summary_table(self, run_kind):
        try:
            if run_kind == "HDFS thesis profile":
                if not HDFS_SUMMARY.exists():
                    return
                with HDFS_SUMMARY.open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                row = next((item for item in rows if item.get("method") == "STC v2 delta=5s"), None)
                if not row:
                    return
                self._set_thesis_summary_defaults("data/HDFS_v1/HDFS.log", HDFS_RECONSTRUCTED, HDFS_SUMMARY)
                self.summary_values["cases"].set(row.get("cases", "N/A"))
                self.summary_values["avg_trace_len"].set(row.get("avg_trace_len", "N/A"))
                self.summary_values["single_event_pct"].set(row.get("single_event_pct", "N/A"))
                self._load_purity_values(row)
                return

            if run_kind == "BGL thesis profile":
                if not BGL_SUMMARY.exists():
                    return
                with BGL_SUMMARY.open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                row = next((item for item in rows if item.get("method") == "STC BGL delta=5s"), None)
                if not row:
                    return
                self._set_thesis_summary_defaults("data/BGL/BGL_2k.log", BGL_RECONSTRUCTED, BGL_SUMMARY)
                self.summary_values["parsed_events"].set(row.get("events", "N/A"))
                self.summary_values["cases"].set(row.get("cases", "N/A"))
                self.summary_values["avg_trace_len"].set(row.get("avg_trace_len", "N/A"))
                self.summary_values["single_event_pct"].set(row.get("single_event_pct", "N/A"))
                self._set_purity_rows_visible(False)
        except Exception as exc:
            self._append_output(f"Could not read thesis summary table: {exc}\n")

    def _refresh_output_buttons(self):
        generic_active = self.current_result_kind == "generic"
        hdfs_active = self.current_result_kind == "HDFS thesis profile"
        bgl_active = self.current_result_kind == "BGL thesis profile"

        self._set_button_state(
            self.open_reconstructed_button,
            "normal" if self._current_reconstructed_path() is not None else "disabled",
        )
        self._set_button_state(
            self.open_summary_button,
            "normal" if self._current_summary_path() is not None else "disabled",
        )

        pm_exists = (
            (generic_active and self.current_generic_pm_path.exists())
            or (hdfs_active and HDFS_PM_RESULTS.exists())
            or (bgl_active and BGL_PM_RESULTS.exists())
        )
        self._set_button_state(self.open_pm_button, "normal" if pm_exists else "disabled")

        visualization_exists = (
            (generic_active and any(path.exists() for path in GENERIC_PROCESS_MODEL_CANDIDATES))
            or (hdfs_active and any(path.exists() for path in PROCESS_MODEL_CANDIDATES))
        )
        self._set_button_state(
            self.open_visualization_button,
            "normal" if visualization_exists else "disabled",
        )

        output_folder = self._current_output_folder()
        self._set_button_state(
            self.open_output_button,
            "normal" if output_folder is not None and output_folder.exists() else "disabled",
        )

    def _open_process_mining_results(self):
        if self.current_result_kind == "generic" and self.current_generic_pm_path.exists():
            self._open_path(self.current_generic_pm_path)
        elif self.current_result_kind == "HDFS thesis profile" and HDFS_PM_RESULTS.exists():
            self._open_path(HDFS_PM_RESULTS)
        elif self.current_result_kind == "BGL thesis profile" and BGL_PM_RESULTS.exists():
            self._open_path(BGL_PM_RESULTS)
        else:
            self._show_missing("No process mining results found yet.")

    def _current_reconstructed_path(self):
        if self.current_result_kind == "generic" and self.current_generic_reconstructed_path.exists():
            return self.current_generic_reconstructed_path
        if self.current_result_kind == "HDFS thesis profile" and HDFS_RECONSTRUCTED.exists():
            return HDFS_RECONSTRUCTED
        if self.current_result_kind == "BGL thesis profile" and BGL_RECONSTRUCTED.exists():
            return BGL_RECONSTRUCTED
        return None

    def _current_summary_path(self):
        if self.current_result_kind == "generic" and self.current_generic_summary_path.exists():
            return self.current_generic_summary_path
        if self.current_result_kind == "HDFS thesis profile" and HDFS_SUMMARY.exists():
            return HDFS_SUMMARY
        if self.current_result_kind == "BGL thesis profile" and BGL_SUMMARY.exists():
            return BGL_SUMMARY
        return None

    def _open_reconstructed_event_log(self):
        path = self._current_reconstructed_path()
        if path is None:
            self._show_missing("No reconstructed event log found yet.")
            return
        self._open_path(path)

    def _open_summary_results(self):
        path = self._current_summary_path()
        if path is None:
            self._show_missing("No summary results found yet.")
            return
        self._open_path(path)

    def _current_output_folder(self):
        if self.current_result_kind == "generic":
            return PROJECT_ROOT / "out_generic"
        if self.current_result_kind == "HDFS thesis profile":
            return PROJECT_ROOT / "out"
        if self.current_result_kind == "BGL thesis profile":
            return PROJECT_ROOT / "out_bgl"
        return None

    def _open_current_output_folder(self):
        folder = self._current_output_folder()
        if folder is None:
            self._show_missing("No output folder is linked to the current result yet. Run processing first.")
            return
        self._open_path(folder)

    def _open_process_model(self):
        if self.current_result_kind == "generic":
            candidates = GENERIC_PROCESS_MODEL_CANDIDATES
        elif self.current_result_kind == "HDFS thesis profile":
            candidates = PROCESS_MODEL_CANDIDATES
        else:
            candidates = []

        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            self._show_missing(
                "Process model image not found. Run processing first. "
                "If Graphviz is not installed, the visualization may not be generated."
            )
            return
        self._open_path(path)

    def _open_path(self, path_or_relative):
        path = Path(path_or_relative)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            self._show_missing(f"Missing path: {path}")
            return
        os.startfile(path)
        self._append_output(f"Opened: {path}\n")

    def _show_missing(self, message):
        self.final_status_var.set(message)
        messagebox.showerror("Missing File", message)

    def mainloop(self):
        self.root.mainloop()


def main():
    app = STCDemoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
