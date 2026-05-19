import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .batch_runner import BatchRunner


DOMAIN_LABELS = {
    "longitudinal_feature": "Longitudinal",
    "lateral_feature": "Lateral",
    "laterall_feature": "Lateral",
    "parking_feature": "Parking",
    "brake_feature": "Brake",
}

DOMAIN_ORDER = {
    "longitudinal_feature": 0,
    "lateral_feature": 1,
    "laterall_feature": 1,
    "parking_feature": 2,
    "brake_feature": 3,
}


class BatchRunnerGUI:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.runner = BatchRunner(self.repo_root)
        self.worker = None
        self.messages = queue.Queue()

        self.root = tk.Tk()
        self.root.title("CARLA XOSC Batch Runner")
        self.root.resizable(True, True)

        self.mode = tk.StringVar(value="single_case")
        self.status = tk.StringVar(value="Ready")
        self.selection_hint = tk.StringVar(value="")
        self.selection_summary = tk.StringVar(value="")

        self.groups = []
        self.jobs = []
        self.jobs_by_case = {}
        self.checked_groups = set()
        self.selected_domain = None
        self.selected_function = None
        self.selected_folder = None
        self.selected_case = None

        self._build_layout()
        self._fit_initial_window()
        self.refresh_data()
        self.root.after(100, self._poll_messages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def run(self):
        self.root.mainloop()

    def _build_layout(self):
        self._configure_style()

        main = ttk.Frame(self.root, padding=6)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        main.rowconfigure(5, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="CARLA XOSC Batch Runner", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.status, style="Status.TLabel").grid(
            row=0, column=1, sticky="e"
        )

        mode_frame = ttk.LabelFrame(main, text="Run Mode", padding=(8, 6))
        mode_frame.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        mode_frame.columnconfigure(4, weight=1)

        for index, (value, label) in enumerate(
            [
                ("single_case", "Single case"),
                ("single_folder", "Single folder"),
                ("multi_folder", "Multi folder"),
                ("all_folders", "All folders in function"),
            ]
        ):
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=value,
                variable=self.mode,
                command=self._on_mode_change,
            ).grid(row=0, column=index, sticky="w", padx=(0, 14))

        ttk.Button(mode_frame, text="Refresh", command=self.refresh_data).grid(
            row=0, column=5, sticky="e"
        )

        info_frame = ttk.Frame(main)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        info_frame.columnconfigure(0, weight=1)

        ttk.Label(info_frame, textvariable=self.selection_hint, style="Hint.TLabel").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(info_frame, textvariable=self.selection_summary, style="Summary.TLabel").grid(
            row=0, column=1, sticky="e", padx=(12, 0)
        )

        content = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        content.grid(row=3, column=0, sticky="nsew")

        self.domain_tree = self._make_tree_panel(
            content,
            title="1. Domain",
            columns=("domain", "functions", "cases"),
            headings=("Domain", "Func", "Cases"),
            widths=(150, 52, 64),
            weight=1,
            click_handler=self._on_domain_click,
        )

        self.function_tree = self._make_tree_panel(
            content,
            title="2. Function",
            columns=("function", "folders", "cases"),
            headings=("Function", "Folders", "Cases"),
            widths=(130, 58, 64),
            weight=1,
            click_handler=self._on_function_click,
        )

        self.folder_tree = self._make_tree_panel(
            content,
            title="3. Scenario Folder",
            columns=("folder", "cases", "check"),
            headings=("Folder", "Cases", "Run"),
            widths=(180, 58, 54),
            weight=2,
            click_handler=self._on_folder_click,
        )

        self.case_tree = self._make_tree_panel(
            content,
            title="4. Case",
            columns=("case", "folder"),
            headings=("Case ID", "Scenario Folder"),
            widths=(220, 260),
            weight=3,
            click_handler=self._on_case_click,
        )

        controls = ttk.Frame(main)
        controls.grid(row=4, column=0, sticky="ew", pady=(6, 6))
        controls.columnconfigure(2, weight=1)

        self.start_btn = ttk.Button(
            controls, text="Start", command=self.start, style="Accent.TButton"
        )
        self.start_btn.grid(row=0, column=0, sticky="w")

        self.stop_btn = ttk.Button(controls, text="Stop/End", command=self.stop, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.progress = ttk.Progressbar(controls, mode="determinate")
        self.progress.grid(row=0, column=2, sticky="ew", padx=12)

        log_frame = ttk.LabelFrame(main, text="Log", padding=6)
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=4, wrap=tk.WORD, relief=tk.FLAT)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _make_tree_panel(self, content, title, columns, headings, widths, weight, click_handler):
        frame = ttk.LabelFrame(content, text=title, padding=6)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        content.add(frame, weight=weight)

        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=9,
        )

        for column, heading, width in zip(columns, headings, widths):
            anchor = tk.CENTER if column in {"functions", "folders", "cases", "check"} else tk.W
            tree.heading(column, text=heading)
            tree.column(
                column,
                width=width,
                minwidth=max(48, min(width, 120)),
                anchor=anchor,
                stretch=column not in {"functions", "folders", "cases", "check"},
            )

        tree.grid(row=0, column=0, sticky="nsew")
        tree.bind("<Button-1>", click_handler)

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Summary.TLabel", foreground="#0f5c9c")
        style.configure("Accent.TButton", padding=(14, 6))

    def _fit_initial_window(self):
        self.root.update_idletasks()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_width = int(screen_width * 0.97)
        max_height = int(screen_height * 0.94)
        min_width = min(920, max_width)
        min_height = min(540, max_height)

        width = min(max(1220, min_width), max_width)
        height = min(max(760, min_height), max_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)

        self.root.minsize(min_width, min_height)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        if screen_width >= 1280 and screen_height >= 720:
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def refresh_data(self):
        self.groups = self.runner.discover_groups()
        self.jobs = self.runner.discover_jobs()
        self.jobs_by_case = {job.job_key: job for job in self.jobs}
        self.checked_groups = {group for group in self.checked_groups if group in self.groups}

        if self.selected_domain not in self._domain_keys():
            self.selected_domain = None
        if self.selected_function not in self._function_keys(self.selected_domain):
            self.selected_function = None
        if self.selected_folder not in self.groups:
            self.selected_folder = None
        if self.selected_case not in self.jobs_by_case:
            self.selected_case = None

        self._reset_progress()
        self._render_all()
        self._log_scan_summary()

    def _reset_progress(self):
        self.progress.config(maximum=100, value=0)

    def _on_mode_change(self):
        mode = self.mode.get()
        self.checked_groups.clear()
        self.selected_case = None
        if mode == "all_folders":
            self.selected_folder = None
            self.checked_groups = set(self._visible_groups())
        self._render_all()

    def _render_all(self):
        self._render_domains()
        self._render_functions()
        self._render_folders()
        self._render_cases()
        self._update_hint()
        self._update_summary()

    def _render_domains(self):
        self.domain_tree.delete(*self.domain_tree.get_children())

        for domain in self._domain_keys():
            function_count = len(self._function_keys(domain))
            case_count = len([job for job in self.jobs if self._job_domain(job) == domain])
            tags = ("selected",) if domain == self.selected_domain else ()
            self.domain_tree.insert(
                "",
                tk.END,
                iid=domain,
                values=(self._domain_label(domain), function_count, case_count),
                tags=tags,
            )

        self._configure_tree_tags(self.domain_tree)
        if self.selected_domain and self.domain_tree.exists(self.selected_domain):
            self.domain_tree.selection_set(self.selected_domain)

    def _render_functions(self):
        self.function_tree.delete(*self.function_tree.get_children())

        for function in self._function_keys(self.selected_domain):
            folders = self._groups_for_function(self.selected_domain, function)
            case_count = len(
                [
                    job
                    for job in self.jobs
                    if self._job_domain(job) == self.selected_domain
                    and self._job_function(job) == function
                ]
            )
            tags = ("selected",) if function == self.selected_function else ()
            self.function_tree.insert(
                "",
                tk.END,
                iid=function,
                values=(function, len(folders), case_count),
                tags=tags,
            )

        self._configure_tree_tags(self.function_tree)
        if self.selected_function and self.function_tree.exists(self.selected_function):
            self.function_tree.selection_set(self.selected_function)

    def _render_folders(self):
        self.folder_tree.delete(*self.folder_tree.get_children())
        mode = self.mode.get()
        counts = self._folder_counts()
        if mode == "all_folders":
            self.checked_groups = set(self._visible_groups())

        for group in self._visible_groups():
            scenario_id = self._group_scenario(group)
            checked = group in self.checked_groups or mode == "all_folders"
            mark = "Yes" if checked else ""
            tags = []

            if mode == "single_folder" and self.selected_folder:
                tags.append("selected" if group == self.selected_folder else "disabled")
            elif mode == "single_case" and self.selected_folder:
                tags.append("selected" if group == self.selected_folder else "disabled")
            elif mode == "multi_folder" and checked:
                tags.append("selected")
            elif mode == "all_folders":
                tags.append("selected")

            self.folder_tree.insert(
                "",
                tk.END,
                iid=group,
                values=(scenario_id, counts.get(group, 0), mark),
                tags=tuple(tags),
            )

        self._configure_tree_tags(self.folder_tree)
        if self.selected_folder and self.folder_tree.exists(self.selected_folder):
            self.folder_tree.selection_set(self.selected_folder)

    def _render_cases(self):
        self.case_tree.delete(*self.case_tree.get_children())
        mode = self.mode.get()

        for job in self._visible_jobs():
            tags = []
            if mode == "single_case" and self.selected_case:
                tags.append("selected" if job.job_key == self.selected_case else "disabled")
            elif mode == "all_folders":
                tags.append("disabled")

            self.case_tree.insert(
                "",
                tk.END,
                iid=job.job_key,
                values=(job.case_id, self._group_scenario(job.group_name)),
                tags=tuple(tags),
            )

        self._configure_tree_tags(self.case_tree)
        if self.selected_case and self.case_tree.exists(self.selected_case):
            self.case_tree.selection_set(self.selected_case)

    @staticmethod
    def _configure_tree_tags(tree):
        tree.tag_configure("disabled", foreground="#9a9a9a")
        tree.tag_configure("selected", foreground="#0f5c9c")

    def _on_domain_click(self, event):
        row = self.domain_tree.identify_row(event.y)
        if not row:
            return "break"

        if self.selected_domain == row:
            self.selected_domain = None
        else:
            self.selected_domain = row
        self.selected_function = None
        self.selected_folder = None
        self.selected_case = None
        self.checked_groups.clear()
        self._render_all()
        return "break"

    def _on_function_click(self, event):
        row = self.function_tree.identify_row(event.y)
        if not row:
            return "break"

        if self.selected_function == row:
            self.selected_function = None
        else:
            self.selected_function = row
        self.selected_folder = None
        self.selected_case = None
        self.checked_groups.clear()
        self._render_all()
        return "break"

    def _on_folder_click(self, event):
        row = self.folder_tree.identify_row(event.y)
        if not row:
            return

        mode = self.mode.get()
        if mode == "all_folders":
            return "break"

        if mode == "multi_folder":
            if row in self.checked_groups:
                self.checked_groups.remove(row)
            else:
                self.checked_groups.add(row)
            self.selected_folder = None
            self.selected_case = None
            self._render_all()
            return "break"

        if mode == "single_folder":
            self.selected_folder = None if self.selected_folder == row else row
            self.selected_case = None
            self._select_scope_from_group(row)
            self._render_all()
            return "break"

        if mode == "single_case":
            if self.selected_folder != row:
                self.selected_folder = row
                self.selected_case = None
                self._select_scope_from_group(row)
                self._render_all()
            return "break"

    def _on_case_click(self, event):
        row = self.case_tree.identify_row(event.y)
        if not row:
            return

        mode = self.mode.get()
        if mode != "single_case":
            return "break"

        if self.selected_case == row:
            self.selected_case = None
        elif not self.selected_case:
            self.selected_case = row
            self.selected_folder = self.jobs_by_case[row].group_name
            self._select_scope_from_group(self.selected_folder)
        self._render_all()
        return "break"

    def _select_scope_from_group(self, group):
        parts = group.split("/")
        if len(parts) >= 2:
            self.selected_domain = parts[0]
            self.selected_function = parts[1]

    def start(self):
        if self.worker and self.worker.is_alive():
            return

        jobs = self._selected_jobs()
        if not jobs:
            if self.mode.get() == "all_folders":
                messagebox.showwarning(
                    "No function selected",
                    "Select one domain and one function before running all folders.",
                )
            else:
                messagebox.showwarning("No scenario", "No scenario selected.")
            return

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.config(maximum=len(jobs), value=0)
        self.status.set("Running")

        self.worker = threading.Thread(target=self._run_worker, args=(jobs,), daemon=True)
        self.worker.start()

    def stop(self):
        self._log("Stop/End requested...")
        self.runner.stop()
        self.stop_btn.config(state=tk.DISABLED)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Batch running", "A batch is running. Stop it and close?"):
                return
        self.runner.shutdown()
        self.root.destroy()

    def _run_worker(self, jobs):
        try:
            self.runner.run(
                jobs,
                keep_support_tools=False,
                on_log=lambda msg: self.messages.put(("log", msg)),
                on_progress=lambda current, total, msg: self.messages.put(
                    ("progress", current, total, msg)
                ),
            )
            self.messages.put(("done", "Batch completed."))
        except Exception as exc:
            self.messages.put(("done", f"ERROR: {exc}"))

    def _poll_messages(self):
        try:
            while True:
                item = self.messages.get_nowait()
                if item[0] == "log":
                    self._log(item[1])
                elif item[0] == "progress":
                    _, current, total, msg = item
                    self.progress.config(maximum=total, value=current)
                    self.status.set(msg)
                elif item[0] == "done":
                    self._log(item[1])
                    self.status.set("Ready")
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_messages)

    def _selected_jobs(self):
        mode = self.mode.get()
        if mode == "all_folders":
            if not self.selected_domain or not self.selected_function:
                return []
            return self.runner.jobs_for_groups(self._visible_groups())

        if mode == "single_case":
            if not self.selected_case:
                return []
            return [self.jobs_by_case[self.selected_case]]

        if mode == "single_folder":
            if not self.selected_folder:
                return []
            return self.runner.jobs_for_groups([self.selected_folder])

        if mode == "multi_folder":
            return self.runner.jobs_for_groups(sorted(self.checked_groups))

        return []

    def _visible_jobs(self):
        if not self.selected_domain or not self.selected_function:
            return []
        if self.mode.get() == "single_case":
            if self.selected_folder:
                return [job for job in self.jobs if job.group_name == self.selected_folder]
            return [
                job
                for job in self.jobs
                if self._job_domain(job) == self.selected_domain
                and (
                    self.selected_function is None
                    or self._job_function(job) == self.selected_function
                )
            ]
        if self.mode.get() == "multi_folder" and self.checked_groups:
            return [job for job in self.jobs if job.group_name in self.checked_groups]
        if self.selected_folder:
            return [job for job in self.jobs if job.group_name == self.selected_folder]
        return [
            job
            for job in self.jobs
            if self._scope_matches(self._job_domain(job), self._job_function(job))
        ]

    def _visible_groups(self):
        if not self.selected_domain or not self.selected_function:
            return []
        return [
            group
            for group in self.groups
            if self._scope_matches(self._group_domain(group), self._group_function(group))
        ]

    def _scope_matches(self, domain, function):
        if self.selected_domain and domain != self.selected_domain:
            return False
        if self.selected_function and function != self.selected_function:
            return False
        return True

    def _domain_keys(self):
        domains = set()
        if self.runner.xosc_root.exists():
            domains.update(path.name for path in self.runner.xosc_root.iterdir() if path.is_dir())
        domains.update(self._group_domain(group) for group in self.groups)
        return sorted(domains, key=lambda item: (DOMAIN_ORDER.get(item, 99), self._domain_label(item)))

    def _function_keys(self, domain):
        if not domain:
            return []
        functions = {
            self._group_function(group)
            for group in self.groups
            if self._group_domain(group) == domain
        }

        domain_path = self.runner.xosc_root / domain
        if domain_path.exists():
            functions.update(path.name for path in domain_path.iterdir() if path.is_dir())
        return sorted(functions)

    def _groups_for_function(self, domain, function):
        return [
            group
            for group in self.groups
            if self._group_domain(group) == domain and self._group_function(group) == function
        ]

    def _folder_counts(self):
        counts = {}
        for job in self.jobs:
            counts[job.group_name] = counts.get(job.group_name, 0) + 1
        return counts

    def _update_hint(self):
        mode = self.mode.get()
        if mode == "all_folders":
            self.selection_hint.set("Select one domain and one function. All folders inside that function will run.")
        elif mode == "multi_folder":
            self.selection_hint.set("Select a domain, select a function, then toggle scenario folders to build the run queue.")
        elif mode == "single_folder":
            self.selection_hint.set("Select a domain, select a function, then choose one scenario folder.")
        else:
            self.selection_hint.set("Select a domain, select a function, choose a scenario folder, then choose one case.")

    def _update_summary(self):
        selected_count = len(self._selected_jobs())
        visible_groups = len(self._visible_groups())
        visible_cases = len(self._visible_jobs())
        self.selection_summary.set(
            f"Selected: {selected_count} | Visible folders: {visible_groups} | Visible cases: {visible_cases}"
        )

    def _log_scan_summary(self):
        domains = self._domain_keys()
        self._log(f"Scan summary: {len(domains)} domains, {len(self.groups)} folders, {len(self.jobs)} cases.")

        for domain in domains:
            functions = self._function_keys(domain)
            self._log(f"*{self._domain_label(domain)}:")
            if not functions:
                self._log("- No functions: 0 folders, 0 cases.")
                continue

            for function in functions:
                folders = self._groups_for_function(domain, function)
                cases = [
                    job
                    for job in self.jobs
                    if self._job_domain(job) == domain and self._job_function(job) == function
                ]
                self._log(f"- {function}: {len(folders)} folders, {len(cases)} cases.")

    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    @staticmethod
    def _domain_label(domain):
        return DOMAIN_LABELS.get(domain, domain)

    @staticmethod
    def _group_domain(group):
        return group.split("/")[0] if group else ""

    @staticmethod
    def _group_function(group):
        parts = group.split("/")
        return parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _group_scenario(group):
        parts = group.split("/")
        return parts[2] if len(parts) > 2 else group

    def _job_domain(self, job):
        return self._group_domain(job.group_name)

    def _job_function(self, job):
        return self._group_function(job.group_name)
