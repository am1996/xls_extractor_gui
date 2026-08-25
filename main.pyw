import math
import os
import glob
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import pandas as pd
from datetime import datetime,timedelta
import dateutil
#------------------ Excursion Recovery Logic ------------------
def analyze_excursions_df(
    df,
    time_col_idx: int,
    val_col_idx: int,
    min_val: float,
    max_val: float,
    challenge_start: str,
    challenge_end: str,
    recovery_time_minutes: float,
    filename: str
):
    all_results = []
    dt_format = '%d-%m-%Y %I:%M:%S %p'
    start_time = pd.to_datetime(challenge_start)
    end_time = pd.to_datetime(challenge_end)
    recovery_limit = pd.Timedelta(minutes=recovery_time_minutes)

    # Extend monitoring window to assess post-challenge recovery
    max_monitoring_time = end_time + recovery_limit

    filename = filename.replace('.csv', '').replace('.xls', '').replace('.xlsx', '').replace('.csv,', '').replace('.','')
    # Parse dates and numerical data
    df.iloc[:, time_col_idx] = pd.to_datetime(df.iloc[:, time_col_idx], errors='coerce', format='mixed')
    df.iloc[:, val_col_idx] = pd.to_numeric(df.iloc[:, val_col_idx], errors='coerce')
    df = df.iloc[df.iloc[:, [time_col_idx, val_col_idx]].notna().all(axis=1).values]
    
    # Filter data to the monitoring window
    mask = (df.iloc[:, time_col_idx] >= start_time) & (df.iloc[:, time_col_idx] <= max_monitoring_time)
    analysis_df = df.loc[mask].sort_values(by=time_col_idx)
    
    in_excursion = False
    excursion_start = None
    excursion_start_val = None
    excursion_count = 0
    
    for _, row in analysis_df.iterrows():
        current_time = row[time_col_idx]
        current_val = row[val_col_idx]
        
        is_out_of_bounds = (current_val < min_val) or (current_val > max_val)
        
        if not in_excursion:
            # Record start of a new excursion within the challenge window
            if is_out_of_bounds and (current_time <= end_time):
                in_excursion = True
                excursion_start = current_time
                excursion_start_val = current_val
                excursion_count += 1
                
        elif in_excursion and not is_out_of_bounds:
            # Record end of excursion (first reading back in bounds)
            in_excursion = False
            recovery_duration = current_time - excursion_start
            recovery_mins = math.round(recovery_duration.total_seconds() / 60.0, 2)
            recovered_in_time = recovery_duration <= recovery_limit
            
            all_results.append({
                "File": filename,
                "Excursion #": excursion_count,
                "Excursion Start": excursion_start.strftime(dt_format),
                "Start Reading": excursion_start_val,
                "Excursion End": current_time.strftime(dt_format),
                "End Reading": current_val,
                "Time to Recover (Minutes)": recovery_mins,
                "Time to Recover (Formatted)": str(recovery_duration),
                "Pass/Fail": "PASS" if recovered_in_time else "FAIL (Exceeded Limit)"
            })
    return pd.DataFrame(all_results)

# ------------------ Core Processing Logic ------------------
def parse_safe(date_val):
    if date_val is None or not str(date_val).strip():
        return None
    try:
        return dateutil.parser.parse(str(date_val))
    except (dateutil.parser.ParserError, TypeError, ValueError):
        return None

def calc_mkt(temps):
    if len(temps) == 0:
        return np.nan
    temps_k = temps + 273.15
    mkt = 10000 / -np.log(np.mean(np.exp(-10000 / temps_k))) - 273.15
    return mkt


def load_file(file_path, rows_to_skip):
    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(file_path, skiprows=rows_to_skip)
    return pd.read_excel(file_path, skiprows=rows_to_skip)


def extract_min_max_avg(
    df,
    start_date,
    end_date,
    date_mode="Single Column",
    date_index=1,
    time_index=None,
    temp_idx=2,
    rh_idx=3,
    has_rh=True,
):

    # Handle Date/Time Parsing based on chosen structure
    try:
        if date_mode == "Separated Columns" and time_index is not None:
            # Combine strings
            combined = df.iloc[:, date_index].astype(str) + " " + df.iloc[:, time_index].astype(str)

            # Parse using dateutil's flexible parser
            df['Date/time'] = combined.apply(lambda x: dateutil.parser.parse(x) if pd.notna(x) else pd.NaT)
        else:
            df["Date/time"] = df.iloc[:, date_index].apply(lambda x: dateutil.parser.parse(str(x)) if pd.notna(x) else pd.NaT)
    except Exception as e:
        raise ValueError(f"Failed to parse Date/Time columns. Check your indexes. Error: {str(e)}")

    # Filter by date range
    s_df = df[(df["Date/time"] >= start_date) & (df["Date/time"] <= end_date)]

    if s_df.empty:
        return np.nan, np.nan, np.nan, "N/A", "N/A", "N/A", "N/A"

    temp_vals = s_df.iloc[:, temp_idx].values
    mkt = calc_mkt(temp_vals)

    try:
        data_min = min(temp_vals)
        data_max = max(temp_vals)
        data_avg = np.mean(temp_vals)
        data_mkt = mkt if not np.isnan(mkt) else "N/A"

        if has_rh and rh_idx is not None:
            rh_vals = s_df.iloc[:, rh_idx].values
            rh_min = min(rh_vals)
            rh_max = max(rh_vals)
            rh_avg = np.mean(rh_vals)
        else:
            rh_min = rh_max = rh_avg = "N/A"

    except Exception:
        data_min = data_max = data_avg = data_mkt = np.nan
        rh_min = rh_max = rh_avg = "N/A"

    return data_min, data_max, data_avg, data_mkt, rh_min, rh_max, rh_avg


import tkinter as tk
from tkinter import ttk

# --- Scrollable Frame Class for Dynamic Content ---
class ScrollableFrame(ttk.Frame):

    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)

        # 1. Create a Canvas and Vertical Scrollbar
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )

        # 2. Scrollable inner frame (where your inputs/widgets go)
        self.scrollable_content = ttk.Frame(self.canvas)

        # 3. Bind events for dynamic scrolling adjustments
        self.scrollable_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_content, anchor="nw"
        )

        # Ensure the inner frame stretches to full width
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(
                self.canvas_window, width=e.width
            ),
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 4. Grid Canvas and Scrollbar layout
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # 5. Enable Mouse Wheel Scrolling
        self.bind_mouse_wheel(self.canvas)
        self.bind_mouse_wheel(self.scrollable_content)

    def bind_mouse_wheel(self, widget):
        widget.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows / macOS
        widget.bind_all("<Button-4>", self._on_mousewheel)  # Linux scroll up
        widget.bind_all("<Button-5>", self._on_mousewheel)  # Linux scroll down

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

# ------------------ GUI Application ------------------
class DataloggerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Datalogger MKT Summary Generator")
        self.root.geometry("816x720")
        self.root.resizable(False, False)

        # 1. Create scrollable container frame
        container = ScrollableFrame(self.root)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # 2. IMPORTANT: Point main_frame to container.scrollable_content!
        main_frame = container.scrollable_content

        # --- Folder Selection ---
        ttk.Label(main_frame, text="Files Folder:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.folder_var = tk.StringVar()
        self.folder_entry = ttk.Entry(
            main_frame, textvariable=self.folder_var, width=45
        )
        self.folder_entry.grid(row=0, column=1, pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_folder).grid(
            row=0, column=2, pady=5
        )

        # --- Save As ---
        ttk.Label(main_frame, text="Save As:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.save_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.save_var, width=45).grid(
            row=1, column=1, pady=5, padx=5
        )
        ttk.Button(main_frame, text="Browse...", command=self.browse_save).grid(
            row=1, column=2, pady=5
        )

        # --- File Extension Filter ---
        ttk.Label(main_frame, text="File Type:").grid(
            row=0, column=3, sticky=tk.W, padx=(10, 2)
        )
        self.ext_var = tk.StringVar(value="xls")
        self.ext_dropdown = ttk.Combobox(
            main_frame,
            textvariable=self.ext_var,
            values=["xls", "xlsx", "csv", "all"],
            state="readonly",
            width=6,
        )
        self.ext_dropdown.grid(row=0, column=4, sticky=tk.W)

        # --- Start Date/Time ---
        ttk.Label(
            main_frame, text="Start Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=2, column=0, sticky=tk.W, pady=8)
        self.start_date_var = tk.StringVar(value= datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        self.start_entry = ttk.Entry(
            main_frame, textvariable=self.start_date_var, width=35
        )
        self.start_entry.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5)

        # --- End Date/Time ---
        ttk.Label(
            main_frame, text="End Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=3, column=0, sticky=tk.W, pady=8)
        self.end_date_var = tk.StringVar(value= datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        self.end_entry = ttk.Entry(
            main_frame, textvariable=self.end_date_var, width=35
        )
        self.end_entry.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=5)

        # --- Column Mappings Configuration ---
        config_frame = ttk.LabelFrame(main_frame, text=" Data Import Settings ")
        config_frame.grid(row=4, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)

        # Rows to Skip configuration
        ttk.Label(config_frame, text="Rows to Skip (Header):").grid(
            row=0, column=0, padx=10, pady=5, sticky=tk.W
        )
        self.skip_rows_var = tk.IntVar(value=11)  # Keeps your default 11 rows skipped
        self.skip_rows_spinbox = ttk.Spinbox(
            config_frame, from_=0, to=100, textvariable=self.skip_rows_var, width=6
        )
        self.skip_rows_spinbox.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        # Date/Time Format Selector
        ttk.Label(config_frame, text="Date/Time Layout:").grid(
            row=1, column=0, padx=10, pady=5, sticky=tk.W
        )
        self.date_mode_var = tk.StringVar(value="Single Column")
        self.date_mode_dropdown = ttk.Combobox(
            config_frame,
            textvariable=self.date_mode_var,
            values=["Single Column", "Separated Columns"],
            state="readonly",
            width=18,
        )
        self.date_mode_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.date_mode_dropdown.bind("<<ComboboxSelected>>", self.toggle_date_mode)

        # Date Column Index Input
        self.date_lbl = ttk.Label(config_frame, text="Date Column Index:")
        self.date_lbl.grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        self.date_col_var = tk.IntVar(value=1)
        self.date_dropdown = ttk.Combobox(
            config_frame, textvariable=self.date_col_var, values=list(range(20)), width=5
        )
        self.date_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)

        # Time Column Index Input
        self.time_lbl = ttk.Label(config_frame, text="Time Column Index:")
        self.time_lbl.grid(row=2, column=2, padx=5, pady=5, sticky=tk.W)
        self.time_col_var = tk.IntVar(value=2)
        self.time_dropdown = ttk.Combobox(
            config_frame, textvariable=self.time_col_var, values=list(range(20)), width=5
        )
        self.time_dropdown.grid(row=2, column=3, padx=5, pady=5, sticky=tk.W)
        
        self.toggle_date_mode()

        # Temp Column Select
        ttk.Label(config_frame, text="Temperature Column Index:").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        self.temp_col_var = tk.IntVar(value=2)
        self.temp_dropdown = ttk.Combobox(
            config_frame, textvariable=self.temp_col_var, values=list(range(20)), width=5
        )
        self.temp_dropdown.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)

        # RH Column Select
        ttk.Label(config_frame, text="RH Column Index:").grid(
            row=4, column=0, padx=10, pady=5, sticky=tk.W
        )
        self.rh_col_var = tk.IntVar(value=3)
        self.rh_dropdown = ttk.Combobox(
            config_frame, textvariable=self.rh_col_var, values=list(range(20)), width=5
        )
        self.rh_dropdown.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)

        # "No RH data" checkbox option
        self.has_rh_var = tk.BooleanVar(value=True)
        self.rh_checkbox = ttk.Checkbutton(
            config_frame,
            text="RH Data Available",
            variable=self.has_rh_var,
            command=self.toggle_rh_state,
        )
        self.rh_checkbox.grid(row=4, column=2, columnspan=2, padx=5, pady=5, sticky=tk.W)

        # --- Status ---
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Arial", 9, "italic"),
            foreground="gray",
        )
        self.status_label.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=5)

        # --- Acceptance Criteria Temperature Note ---
        ac_temp_frame = ttk.LabelFrame(main_frame, text=" Acceptance Criteria Temperature")
        ac_temp_frame.grid(row=5, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)
        ttk.Label(
            ac_temp_frame, text="Temp LCL:"
        ).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.lcl_temp = tk.StringVar(value="18")
        ttk.Entry(ac_temp_frame, textvariable=self.lcl_temp, width=10).grid(
            row=0, column=1, sticky=tk.W, padx=5
        )
        ttk.Label(
            ac_temp_frame, text="Temp UCL:"
        ).grid(row=0, column=3, sticky=tk.W, pady=8)
        self.ucl_temp = tk.StringVar(value="25")
        ttk.Entry(ac_temp_frame, textvariable=self.ucl_temp, width=10).grid(
            row=0, column=4, sticky=tk.W, padx=5
        )
        # --- Acceptance Criteria Humidity Note ---
        ac_rh_frame = ttk.LabelFrame(main_frame, text=" Acceptance Criteria Humidity")
        ac_rh_frame.grid(row=6, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)
        ttk.Label(
            ac_rh_frame, text="Humidity LCL:"
        ).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.lcl_rh = tk.StringVar(value="60")
        self.lcl_rh_entry = ttk.Entry(ac_rh_frame, textvariable=self.lcl_rh, width=10)
        self.lcl_rh_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(
            ac_rh_frame, text="Humidity UCL:"
        ).grid(row=0, column=3, sticky=tk.W, pady=8)
        self.ucl_rh = tk.StringVar(value="70")
        self.ucl_rh_entry = ttk.Entry(ac_rh_frame, textvariable=self.ucl_rh, width=10)
        self.ucl_rh_entry.grid(
            row=0, column=4, sticky=tk.W, padx=5
        )
        # --- Open Door challenge test ---
        open_door_frame = ttk.LabelFrame(main_frame, text="Open Door Challenge Test")
        open_door_frame.grid(row=7, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)
        ttk.Label(
            open_door_frame, text="Start Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.od_start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        self.od_start_entry = ttk.Entry(
            open_door_frame, textvariable=self.od_start_var, width=35
        )
        self.od_start_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=5)
        self.od_end_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        ttk.Label(
            open_door_frame, text="End Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=1, column=0, sticky=tk.W, pady=8)
        self.od_end_entry = ttk.Entry(
            open_door_frame, textvariable=self.od_end_var, width=35
        )
        self.od_end_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5)
        # recovery time for open door challenge test
        self.recovery_od = tk.StringVar(value="60")
        ttk.Label(
            open_door_frame, text="Recovery Time (minutes):"
        ).grid(row=2, column=0, sticky=tk.W, pady=8)
        self.od_rt_entry = ttk.Entry(open_door_frame, textvariable=self.recovery_od, width=10)
        self.od_rt_entry.grid(
            row=2, column=1, sticky=tk.W, padx=5
        )
        ttk.Label(
            open_door_frame, text="Enable/Disable OD Challenge Test:"
        ).grid(row=3, column=0, sticky=tk.W, pady=8)
        self.od_enabled_var = tk.BooleanVar(value=True)
        self.od_checkbox = ttk.Checkbutton(
            open_door_frame,
            text="OD Challenge Test Enabled",
            variable=self.od_enabled_var,
            command=self.toggle_od_state
        ).grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W)

        # --- Power Failure challenge test ---
        power_failure_frame = ttk.LabelFrame(main_frame, text="Power Failure Challenge Test")
        power_failure_frame.grid(row=8, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)
        ttk.Label(
            power_failure_frame, text="Start Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=0, column=0, sticky=tk.W, pady=8)

        self.pf_start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        self.pf_start_entry = ttk.Entry(
            power_failure_frame, textvariable=self.pf_start_var, width=35
        )
        self.pf_start_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=5)

        self.pf_end_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
        ttk.Label(
            power_failure_frame, text="End Date/Time:\n(YYYY-MM-DD HH:MM:SS AM/PM)"
        ).grid(row=1, column=0, sticky=tk.W, pady=8)
        self.pf_end_entry = ttk.Entry(
            power_failure_frame, textvariable=self.pf_end_var, width=35
        )
        self.pf_end_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5)

        self.recovery_pf = tk.StringVar(value="60")
        ttk.Label(
            power_failure_frame, text="Recovery Time (minutes):"
        ).grid(row=2, column=0, sticky=tk.W, pady=8)
        self.pf_rt_entry = ttk.Entry(power_failure_frame, textvariable=self.recovery_pf, width=10)
        self.pf_rt_entry.grid(
            row=2, column=1, sticky=tk.W, padx=5
        )

        ttk.Label(
            power_failure_frame, text="Enable/Disable Power Failure Challenge Test:"
        ).grid(row=3, column=0, sticky=tk.W, pady=8)
        self.pf_enabled_var = tk.BooleanVar(value=True)
        self.pf_checkbox = ttk.Checkbutton(
            power_failure_frame,
            text="Power Failure Challenge Test Enabled",
            variable=self.pf_enabled_var,
            command=self.toggle_pf_state
        ).grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W)

        # --- Action Button ---
        self.run_btn = ttk.Button(
            main_frame, text="Generate Summary", command=self.process_files
        )
        self.run_btn.grid(row=9, column=0, columnspan=3, pady=5, ipady=4)

    def toggle_date_mode(self, event=None):
        if self.date_mode_var.get() == "Separated Columns":
            self.time_lbl.grid()
            self.time_dropdown.grid()
            self.date_lbl.config(text="Date Column Index:")
        else:
            self.time_lbl.grid_remove()
            self.time_dropdown.grid_remove()
            self.date_lbl.config(text="Date/Time Column Index:")

    def toggle_rh_state(self):
        if self.has_rh_var.get():
            self.rh_dropdown.config(state="normal")
            self.lcl_rh_entry.config(state="normal")
            self.ucl_rh_entry.config(state="normal")
        else:
            self.rh_dropdown.config(state="disabled")
            self.lcl_rh_entry.config(state="disabled")
            self.ucl_rh_entry.config(state="disabled")

    def toggle_od_state(self):
        if self.od_enabled_var.get():
            self.od_start_entry.config(state="normal")
            self.od_end_entry.config(state="normal")
            self.od_rt_entry.config(state="normal")
        else:
            self.od_start_entry.config(state="disabled")
            self.od_end_entry.config(state="disabled")
            self.od_rt_entry.config(state="disabled")

    def toggle_pf_state(self):
        if self.pf_enabled_var.get():
            self.pf_start_entry.config(state="normal")
            self.pf_end_entry.config(state="normal")
            self.pf_rt_entry.config(state="normal")
        else:
            self.pf_start_entry.config(state="disabled")
            self.pf_end_entry.config(state="disabled")
            self.pf_rt_entry.config(state="disabled")

    def browse_folder(self):
        selected_dir = filedialog.askdirectory(title="Select folder containing data files")
        if selected_dir:
            self.folder_var.set(os.path.normpath(selected_dir))

    def browse_save(self):
        selected_file = filedialog.asksaveasfilename(
            title="Save output as",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="min_max_summary",
        )
        if selected_file:
            self.save_var.set(os.path.normpath(selected_file))
        
    def process_files(self):
        od_frame = None
        folder = self.folder_var.get()
        start_date = self.start_date_var.get()
        end_date = self.end_date_var.get()

        # Dynamic variable pulls
        rows_to_skip = self.skip_rows_var.get()
        date_mode = self.date_mode_var.get()
        date_idx = self.date_col_var.get()
        time_idx = self.time_col_var.get() if date_mode == "Separated Columns" else None

        temp_idx = self.temp_col_var.get()
        rh_idx = self.rh_col_var.get() if self.has_rh_var.get() else None
        has_rh = self.has_rh_var.get()

        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return

        ext = self.ext_var.get()
        patterns = ["*.xls", "*.xlsx", "*.csv"] if ext == "all" else [f"*.{ext}"]
        files = [f for p in patterns for f in glob.glob(os.path.join(folder, p))]

        if not files:
            messagebox.showerror("Error", f"No {ext.upper()} files found in:\n{folder}")
            return

        self.status_var.set("Processing files... Please wait.")
        self.root.update_idletasks()

        cols = [
            "Datalogger",
            "Min Temp [°C]",
            "Max Temp [°C]",
            "Avg Temp [°C]",
            "MKT",
            "RH Min [%]",
            "RH Max [%]",
            "RH Avg [%]",
        ]
        main_study_frame = pd.DataFrame(columns=cols)
        od_frame = pd.DataFrame(columns=cols)
        pf_frame = pd.DataFrame(columns=cols)
        for f in files:
            df = load_file(f, rows_to_skip)
            ms_data_min, ms_data_max, ms_data_avg, ms_data_mkt, ms_rh_min, ms_rh_max, ms_rh_avg = (
                extract_min_max_avg(
                    df,
                    start_date,
                    end_date,
                    date_mode=date_mode,
                    date_index=date_idx,
                    time_index=time_idx,
                    temp_idx=temp_idx,
                    rh_idx=rh_idx,
                    has_rh=has_rh,
                )
            )
            new_row_ms = pd.DataFrame(
                {
                    "Datalogger": Path(f).stem,
                    "Min Temp [°C]": ms_data_min,
                    "Max Temp [°C]": ms_data_max,
                    "Avg Temp [°C]": ms_data_avg,
                    "MKT": ms_data_mkt,
                    "RH Min [%]": ms_rh_min,
                    "RH Max [%]": ms_rh_max,
                    "RH Avg [%]": ms_rh_avg,
                },
                index=[0],
            )
            main_study_frame = pd.concat([main_study_frame, new_row_ms], ignore_index=True)
            valid_dates = [
                parse_safe(self.od_end_var.get()),
                parse_safe(self.pf_end_var.get()),
                parse_safe(end_date),
            ]
            end_study_date = max([d for d in valid_dates if d is not None]) + timedelta(minutes=int(self.recovery_pf.get()) if self.pf_enabled_var.get() else 60)
            if self.od_enabled_var.get():
                od_data_min, od_data_max, od_data_avg, od_data_mkt, od_rh_min, od_rh_max, od_rh_avg = (
                    extract_min_max_avg(
                        df,
                        self.od_start_var.get(),
                        self.od_end_var.get(),
                        date_mode=date_mode,
                        date_index=date_idx,
                        time_index=time_idx,
                        temp_idx=temp_idx,
                        rh_idx=rh_idx,
                        has_rh=has_rh,
                    )
                )
                new_row_od = pd.DataFrame(
                    {
                        "Datalogger": Path(f).stem,
                        "Min Temp [°C]": od_data_min,
                        "Max Temp [°C]": od_data_max,
                        "Avg Temp [°C]": od_data_avg,
                        "MKT": od_data_mkt,
                        "RH Min [%]": od_rh_min,
                        "RH Max [%]": od_rh_max,
                        "RH Avg [%]": od_rh_avg,
                    },
                    index=[0],
                )
                od_frame = pd.concat([od_frame, new_row_od], ignore_index=True)
            if self.pf_enabled_var.get():
                print(type(int(self.recovery_pf.get())))
                
                pf_data_min, pf_data_max, pf_data_avg, pf_data_mkt, pf_rh_min, pf_rh_max, pf_rh_avg = (
                    extract_min_max_avg(
                        df,
                        self.pf_start_var.get(),
                        self.pf_end_var.get(),
                        date_mode=date_mode,
                        date_index=date_idx,
                        time_index=time_idx,
                        temp_idx=temp_idx,
                        rh_idx=rh_idx,
                        has_rh=has_rh,
                    )
                )
                new_row_pf = pd.DataFrame(
                    {
                        "Datalogger": Path(f).stem,
                        "Min Temp [°C]": pf_data_min,
                        "Max Temp [°C]": pf_data_max,
                        "Avg Temp [°C]": pf_data_avg,
                        "MKT": pf_data_mkt,
                        "RH Min [%]": pf_rh_min,
                        "RH Max [%]": pf_rh_max,
                        "RH Avg [%]": pf_rh_avg,
                    },
                    index=[0],
                )
                pf_frame = pd.concat([pf_frame, new_row_pf], ignore_index=True)
                if self.lcl_temp.get() is None:
                    messagebox.showerror("Error", "Please enter a valid LCL temperature for Power Failure Challenge Test.")
                if self.ucl_temp.get() is None:
                    messagebox.showerror("Error", "Please enter a valid UCL temperature for Power Failure Challenge Test.")
                excursions_temp = analyze_excursions_df(
                    df,
                    time_idx,
                    temp_idx,
                    int(self.lcl_temp.get()),
                    int(self.ucl_temp.get()),
                    str(start_date),
                    str(end_study_date),
                    int(self.recovery_pf.get()) if self.pf_enabled_var.get() else 60,
                    filename=Path(f).stem
                )
                temp_excursions = pd.concat([temp_excursions, excursions_temp], ignore_index=True)
                if self.has_rh_var.get():
                    if self.lcl_rh.get() is None:
                        messagebox.showerror("Error", "Please enter a valid LCL humidity for Power Failure Challenge Test.")
                    if self.ucl_rh.get() is None:
                        messagebox.showerror("Error", "Please enter a valid UCL humidity for Power Failure Challenge Test.")
                    excursions_rh = analyze_excursions_df(
                        df,
                        time_idx,
                        rh_idx,
                        int(self.lcl_rh.get()),
                        int(self.ucl_rh.get()),
                        str(start_date),
                        str(end_study_date),
                        int(self.recovery_pf.get()) if self.pf_enabled_var.get() else 60,
                        filename=Path(f).stem
                    )
                    rh_excursions = pd.concat([rh_excursions, excursions_rh], ignore_index=True)
        ms_analysis_df = main_study_frame.copy()
        ms_analysis_df["MKT"] = pd.to_numeric(ms_analysis_df["MKT"], errors="coerce")
        if not has_rh:
            metrics = (
                ms_analysis_df.drop(columns=["RH Min [%]", "RH Max [%]", "RH Avg [%]"])
                .iloc[:, 1:]
                .agg(["min", "max", "mean"])
            )
        else:
            ms_analysis_df["RH Min [%]"] = pd.to_numeric(ms_analysis_df["RH Min [%]"], errors="coerce")
            ms_analysis_df["RH Max [%]"] = pd.to_numeric(ms_analysis_df["RH Max [%]"], errors="coerce")
            ms_analysis_df["RH Avg [%]"] = pd.to_numeric(ms_analysis_df["RH Avg [%]"], errors="coerce")
            metrics = ms_analysis_df.iloc[:, 1:].agg(["min", "max", "mean"])

        if self.od_enabled_var.get():
            od_analysis_df = od_frame.copy()
            od_analysis_df["MKT"] = pd.to_numeric(od_analysis_df["MKT"], errors="coerce")
            if not has_rh:
                od_metrics = (
                    od_analysis_df.drop(columns=["RH Min [%]", "RH Max [%]", "RH Avg [%]"])
                    .iloc[:, 1:]
                    .agg(["min", "max", "mean"])
                )
            else:
                od_analysis_df["RH Min [%]"] = pd.to_numeric(od_analysis_df["RH Min [%]"], errors="coerce")
                od_analysis_df["RH Max [%]"] = pd.to_numeric(od_analysis_df["RH Max [%]"], errors="coerce")
                od_analysis_df["RH Avg [%]"] = pd.to_numeric(od_analysis_df["RH Avg [%]"], errors="coerce")
                od_metrics = od_analysis_df.iloc[:, 1:].agg(["min", "max", "mean"])
            od_frame = pd.concat([od_frame, od_metrics])
            od_frame.iloc[-3:, 0] = ["Min", "Max", "Avg"]

        if self.pf_enabled_var.get():
            pf_analysis_df = pf_frame.copy()
            pf_analysis_df["MKT"] = pd.to_numeric(pf_analysis_df["MKT"], errors="coerce")
            if not has_rh:
                pf_metrics = (
                    pf_analysis_df.drop(columns=["RH Min [%]", "RH Max [%]", "RH Avg [%]"])
                    .iloc[:, 1:]
                    .agg(["min", "max", "mean"])
                )
            else:
                pf_analysis_df["RH Min [%]"] = pd.to_numeric(pf_analysis_df["RH Min [%]"], errors="coerce")
                pf_analysis_df["RH Max [%]"] = pd.to_numeric(pf_analysis_df["RH Max [%]"], errors="coerce")
                pf_analysis_df["RH Avg [%]"] = pd.to_numeric(pf_analysis_df["RH Avg [%]"], errors="coerce")
                pf_metrics = pf_analysis_df.iloc[:, 1:].agg(["min", "max", "mean"])
            pf_frame = pd.concat([pf_frame, pf_metrics])
            pf_frame.iloc[-3:, 0] = ["Min", "Max", "Avg"]

        main_study_frame = pd.concat([main_study_frame, metrics])
        main_study_frame.iloc[-3:, 0] = ["Min", "Max", "Avg"]

        save_path = self.save_var.get().strip()
        output_path = save_path if save_path else os.path.join(folder, "min_max_summary.xlsx")
        with pd.ExcelWriter(output_path) as writer:
            main_study_frame.to_excel(writer, sheet_name= "Main Study Summary",index=False)
            if od_frame is not None and not od_frame.empty:
                od_frame.to_excel(writer, sheet_name="Open Door Challenge", index=False)
            if self.pf_enabled_var.get() and not pf_frame.empty:
                pf_frame.to_excel(writer, sheet_name="Power Failure Challenge", index=False)
            if temp_excursions is not None and not temp_excursions:
                temp_excursions.to_excel(writer, sheet_name="Temp Excursions", index=False)
            if rh_excursions is not None and not rh_excursions.empty:
                rh_excursions.to_excel(writer, sheet_name="RH Excursions", index=False)


        self.status_var.set("Ready")
        messagebox.showinfo("Success", f"Summary saved successfully to:\n{output_path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DataloggerApp(root)
    root.mainloop()