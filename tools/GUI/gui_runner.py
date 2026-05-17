import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .batch_runner import BatchRunner


class BatchRunnerGUI:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.runner = BatchRunner(self.repo_root)
        self.worker = None
        self.messages = queue.Queue()

        self.root = tk.Tk()
        self.root.title("CARLA XOSC Batch Runner")
        self.root.geometry("1120x720")
        self.root.minsize(980, 620)

        self.mode = tk.StringVar(value="single_case")
        self.status = tk.StringVar(value="Sẵn sàng")
        self.selection_hint = tk.StringVar(value="")

        self.groups = []
        self.jobs = []
        self.jobs_by_case = {}
        self.checked_groups = set()
        self.selected_folder = None
        self.selected_case = None

        self._build_layout()
        self.refresh_data()
        self.root.after(100, self._poll_messages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def run(self):
        self.root.mainloop()

    def _build_layout(self):
        self._configure_style()

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)

        ttk.Label(header, text="CARLA XOSC Batch Runner", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status, style="Status.TLabel").pack(side=tk.RIGHT)

        mode_frame = ttk.LabelFrame(main, text="Chế độ chạy", padding=(10, 8))
        mode_frame.pack(fill=tk.X, pady=(8, 8))

        for value, label in [
            ("single_case", "Single case"),
            ("single_folder", "Single folder"),
            ("multi_folder", "Multi folder"),
            ("all_folders", "All folders"),
        ]:
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=value,
                variable=self.mode,
                command=self._on_mode_change,
            ).pack(side=tk.LEFT, padx=(0, 18))

        ttk.Button(mode_frame, text="Bỏ chọn", command=self.clear_selection).pack(side=tk.RIGHT)
        ttk.Button(mode_frame, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT, padx=(0, 8))

        ttk.Label(main, textvariable=self.selection_hint, style="Hint.TLabel").pack(fill=tk.X, pady=(0, 6))

        content = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)

        folder_frame = ttk.LabelFrame(content, text="Folder test case", padding=8)
        content.add(folder_frame, weight=1)

        self.folder_tree = ttk.Treeview(
            folder_frame,
            columns=("folder", "count", "check"),
            show="headings",
            selectmode="browse",
            height=16,
        )
        self.folder_tree.heading("folder", text="Folder")
        self.folder_tree.heading("count", text="Cases")
        self.folder_tree.heading("check", text="Chọn")
        self.folder_tree.column("folder", width=210, minwidth=160, stretch=True)
        self.folder_tree.column("count", width=58, anchor=tk.CENTER, stretch=False)
        self.folder_tree.column("check", width=58, anchor=tk.CENTER, stretch=False)
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.folder_tree.bind("<Button-1>", self._on_folder_click)

        folder_scroll = ttk.Scrollbar(folder_frame, orient=tk.VERTICAL, command=self.folder_tree.yview)
        folder_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_tree.configure(yscrollcommand=folder_scroll.set)

        case_frame = ttk.LabelFrame(content, text="Scenario .xosc", padding=8)
        content.add(case_frame, weight=2)

        self.case_tree = ttk.Treeview(
            case_frame,
            columns=("case", "folder"),
            show="headings",
            selectmode="browse",
            height=16,
        )
        self.case_tree.heading("case", text="Case ID")
        self.case_tree.heading("folder", text="Folder")
        self.case_tree.column("case", width=360, minwidth=240, stretch=True)
        self.case_tree.column("folder", width=160, minwidth=120, stretch=False)
        self.case_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.case_tree.bind("<Button-1>", self._on_case_click)

        case_scroll = ttk.Scrollbar(case_frame, orient=tk.VERTICAL, command=self.case_tree.yview)
        case_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.case_tree.configure(yscrollcommand=case_scroll.set)

        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, pady=(10, 8))

        self.start_btn = ttk.Button(controls, text="Start", command=self.start, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(controls, text="Stop/End", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.progress = ttk.Progressbar(controls, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)

        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=9, wrap=tk.WORD, relief=tk.FLAT)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Accent.TButton", padding=(14, 6))

    def refresh_data(self):
        self.groups = self.runner.discover_groups()
        self.jobs = self.runner.discover_jobs()
        self.jobs_by_case = {job.case_id: job for job in self.jobs}
        self.checked_groups = {group for group in self.checked_groups if group in self.groups}
        self.selected_folder = self.selected_folder if self.selected_folder in self.groups else None
        self.selected_case = self.selected_case if self.selected_case in self.jobs_by_case else None
        self._render_all()
        self._log(f"Đã scan {len(self.groups)} folder, {len(self.jobs)} case.")

    def clear_selection(self):
        self.checked_groups.clear()
        self.selected_folder = None
        self.selected_case = None
        self._render_all()

    def _on_mode_change(self):
        mode = self.mode.get()
        self.checked_groups.clear()
        self.selected_folder = None
        self.selected_case = None
        if mode == "all_folders":
            self.checked_groups = set(self.groups)
        self._render_all()

    def _render_all(self):
        self._render_folders()
        self._render_cases()
        self._update_hint()

    def _render_folders(self):
        self.folder_tree.delete(*self.folder_tree.get_children())
        counts = self._folder_counts()
        mode = self.mode.get()

        for group in self.groups:
            checked = group in self.checked_groups or mode == "all_folders"
            mark = "☑" if checked else "☐"
            tags = []
            if mode == "single_folder" and self.selected_folder:
                tags.append("selected" if group == self.selected_folder else "disabled")
            elif mode == "single_case" and self.selected_case:
                tags.append("selected" if group == self.selected_folder else "disabled")
            elif mode == "single_case" and self.selected_folder:
                if group == self.selected_folder:
                    tags.append("selected")
            elif mode == "all_folders":
                tags.append("selected")
            elif mode == "multi_folder" and checked:
                tags.append("selected")

            self.folder_tree.insert("", tk.END, iid=group, values=(group, counts.get(group, 0), mark), tags=tuple(tags))

        self.folder_tree.tag_configure("disabled", foreground="#9a9a9a")
        self.folder_tree.tag_configure("selected", foreground="#0f5c9c")

        if self.selected_folder and self.folder_tree.exists(self.selected_folder):
            self.folder_tree.selection_set(self.selected_folder)

    def _render_cases(self):
        self.case_tree.delete(*self.case_tree.get_children())
        mode = self.mode.get()
        jobs = self._visible_jobs()

        for job in jobs:
            tags = []
            if mode == "single_case" and self.selected_case:
                tags.append("selected" if job.case_id == self.selected_case else "disabled")
            elif mode == "all_folders":
                tags.append("disabled")

            self.case_tree.insert("", tk.END, iid=job.case_id, values=(job.case_id, job.group_name), tags=tuple(tags))

        self.case_tree.tag_configure("disabled", foreground="#9a9a9a")
        self.case_tree.tag_configure("selected", foreground="#0f5c9c")

        if self.selected_case and self.case_tree.exists(self.selected_case):
            self.case_tree.selection_set(self.selected_case)

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
            if self.selected_folder and row != self.selected_folder:
                return "break"
            self.selected_folder = row
            self.selected_case = None
            self._render_all()
            return "break"

        if mode == "single_case":
            if self.selected_case:
                return "break"
            self.selected_folder = row
            self._render_all()
            return "break"

    def _on_case_click(self, event):
        row = self.case_tree.identify_row(event.y)
        if not row:
            return

        mode = self.mode.get()
        if mode == "all_folders":
            return "break"

        if mode == "single_case":
            if self.selected_case and row != self.selected_case:
                return "break"
            self.selected_case = row
            self.selected_folder = self.jobs_by_case[row].group_name
            self._render_all()
            return "break"

        return "break"

    def start(self):
        if self.worker and self.worker.is_alive():
            return

        jobs = self._selected_jobs()
        if not jobs:
            messagebox.showwarning("No scenario", "Chưa chọn scenario để chạy.")
            return

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.config(maximum=len(jobs), value=0)
        self.status.set("Đang chạy")

        self.worker = threading.Thread(target=self._run_worker, args=(jobs,), daemon=True)
        self.worker.start()

    def stop(self):
        self._log("Đang yêu cầu Stop/End...")
        self.runner.stop()
        self.stop_btn.config(state=tk.DISABLED)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Đang chạy", "Batch đang chạy. Dừng và đóng GUI?"):
                return
        self.runner.shutdown()
        self.root.destroy()

    def _run_worker(self, jobs):
        try:
            self.runner.run(
                jobs,
                keep_support_tools=False,
                on_log=lambda msg: self.messages.put(("log", msg)),
                on_progress=lambda current, total, msg: self.messages.put(("progress", current, total, msg)),
            )
            self.messages.put(("done", "Hoàn tất batch."))
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
                    self.status.set("Sẵn sàng")
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_messages)

    def _selected_jobs(self):
        mode = self.mode.get()
        if mode == "all_folders":
            return self.jobs

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
        mode = self.mode.get()
        if mode == "single_folder" and self.selected_folder:
            return [job for job in self.jobs if job.group_name == self.selected_folder]
        if mode == "multi_folder" and self.checked_groups:
            return [job for job in self.jobs if job.group_name in self.checked_groups]
        if mode == "single_case" and self.selected_folder and not self.selected_case:
            return [job for job in self.jobs if job.group_name == self.selected_folder]
        return self.jobs

    def _folder_counts(self):
        counts = {}
        for job in self.jobs:
            counts[job.group_name] = counts.get(job.group_name, 0) + 1
        return counts

    def _update_hint(self):
        mode = self.mode.get()
        if mode == "single_case":
            if self.selected_case:
                self.selection_hint.set(f"Đã khóa case {self.selected_case}. Bấm 'Bỏ chọn' để đổi case.")
            else:
                self.selection_hint.set("Chọn một case .xosc. Sau khi chọn, các case còn lại sẽ bị làm mờ.")
        elif mode == "single_folder":
            if self.selected_folder:
                self.selection_hint.set(f"Đã khóa folder {self.selected_folder}. Bấm 'Bỏ chọn' để đổi folder.")
            else:
                self.selection_hint.set("Chọn một folder. Sau khi chọn, các folder còn lại sẽ bị làm mờ.")
        elif mode == "multi_folder":
            self.selection_hint.set("Tick ☑ các folder cần chạy. Danh sách case bên phải chỉ hiển thị các folder đã chọn.")
        else:
            self.selection_hint.set("All folders: tất cả folder đã được chọn và khóa. Bấm Start để chạy toàn bộ.")

    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
