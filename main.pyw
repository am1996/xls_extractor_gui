import os
import glob
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import pandas as pd
from datetime import datetime

#------------------ Excursion Recovery Logic ------------------
def _process_file(
    filepath,
    challenge_start, challenge_end, allowed_recovery,
    channel, temp_min, temp_max, rh_min, rh_max,
    header_row, date_col, temp_col, rh_col
):
    logger_number = os.path.splitext(os.path.basename(filepath))[0].replace(".", "")

    df = pd.read_excel(filepath, header=header_row)
    df = df.iloc[:, 1:4].copy()
    df.columns = [date_col, temp_col, rh_col]
    df = df.dropna()
    df[date_col] = pd.to_datetime(df[date_col], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    df = df.dropna(subset=[date_col]).reset_index(drop=True)
    df = df[(df[date_col] >= challenge_start) & (df[date_col] <= challenge_end)].reset_index(drop=True)

    if df.empty:
        return []

    def extract(df, col, low, high):
        in_excursion = (df[col] < low) | (df[col] > high)
        records = []
        i = 0
        while i < len(df):
            if in_excursion.iloc[i]:
                start_time = df[date_col].iloc[i]
                start_val  = df[col].iloc[i]
                direction  = "HIGH" if df[col].iloc[i] > high else "LOW"
                j = i + 1
                while j < len(df) and in_excursion.iloc[j]:
                    j += 1
                end_idx          = j - 1
                excursion_end    = df[date_col].iloc[end_idx]
                if j < len(df):
                    recovery_time = df[date_col].iloc[j]
                    recovered     = True
                    duration      = recovery_time - start_time
                else:
                    recovery_time = pd.NaT
                    recovered     = False
                    duration      = excursion_end - start_time
                within_allowed = (duration <= allowed_recovery) if recovered else False
                records.append({
                    "Direction": direction,
                    "Excursion Start": start_time,
                    "Excursion End": excursion_end,
                    "Start Value": round(start_val, 2),
                    "Recovered": recovered,
                    "Recovery Time": recovery_time,
                    "Recovery Duration": duration,
                    "Within Allowed Recovery": within_allowed
                })
                i = j
            else:
                i += 1
        return records

def analyze_excursions(
    directory,
    challenge_start,
    challenge_end,
    allowed_recovery,
    channel="temp_and_rh",
    temp_min=None, temp_max=None,
    rh_min=None, rh_max=None,
    header_row=11,
    date_col=1,
    temp_col=2,
    rh_col=3
):
    """
    directory        : path to folder containing excel files (.xls / .xlsx)
    channel          : 'temp' | 'rh' | 'temp_and_rh'
    challenge_start  : str  e.g. '2026-07-16 04:24:51 PM'
    challenge_end    : str  e.g. '2026-07-26 03:34:51 PM'
    allowed_recovery : int  minutes e.g. 30
    """
    challenge_start  = pd.to_datetime(challenge_start, format="%Y-%m-%d %I:%M:%S %p")
    challenge_end    = pd.to_datetime(challenge_end,   format="%Y-%m-%d %I:%M:%S %p")
    allowed_recovery = pd.Timedelta(minutes=allowed_recovery)
    channel          = channel.lower().strip()

    files = glob.glob(os.path.join(directory, "*.xls")) + \
            glob.glob(os.path.join(directory, "*.xlsx"))

    if not files:
        print("No Excel files found in directory.")
        return pd.DataFrame()

    all_records = []
    for filepath in files:
        try:
            all_records.extend(_process_file(
                filepath, challenge_start, challenge_end, allowed_recovery,
                channel, temp_min, temp_max, rh_min, rh_max,
                header_row, date_col, temp_col, rh_col
            ))
        except Exception as e:
            print(f"Skipping {os.path.basename(filepath)}: {e}")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    out = pd.DataFrame(all_records).sort_values(["Logger", "Excursion Start"]).reset_index(drop=True)

    fmt = "%Y-%m-%d %I:%M:%S %p"
    for col in ["Excursion Start", "Excursion End", "Recovery Time"]:
        out[col] = out[col].apply(lambda x: x.strftime(fmt) if pd.notna(x) else "N/A")

    print(out.to_string() if not out.empty else "No excursions found.")
    return out

# ------------------ Core Processing Logic ------------------
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
    file_path,
    start_date,
    end_date,
    date_mode="Single Column",
    date_index=1,
    time_index=None,
    rows_to_skip=11,
    temp_idx=2,
    rh_idx=3,
    has_rh=True,
):

    df = load_file(file_path, rows_to_skip)

    # Handle Date/Time Parsing based on chosen structure
    try:
        if date_mode == "Separated Columns" and time_index is not None:
            df["Date/time"] = pd.to_datetime(
                df.iloc[:, date_index].astype(str) + " " + df.iloc[:, time_index].astype(str),
                format="%m/%d/%Y %I:%M:%S %p",
                errors='coerce'
            )
        else:
            df["Date/time"] = pd.to_datetime(
                df.iloc[:, date_index], 
                format="%m/%d/%Y %I:%M:%S %p",
                errors='coerce'
            )
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
        self.lcl_temp = tk.StringVar(value="")
        ttk.Entry(ac_temp_frame, textvariable=self.lcl_temp, width=10).grid(
            row=0, column=1, sticky=tk.W, padx=5
        )
        ttk.Label(
            ac_temp_frame, text="Temp UCL:"
        ).grid(row=0, column=3, sticky=tk.W, pady=8)
        self.ucl_temp = tk.StringVar(value="")
        ttk.Entry(ac_temp_frame, textvariable=self.ucl_temp, width=10).grid(
            row=0, column=4, sticky=tk.W, padx=5
        )
        # --- Acceptance Criteria Humidity Note ---
        ac_rh_frame = ttk.LabelFrame(main_frame, text=" Acceptance Criteria Humidity")
        ac_rh_frame.grid(row=6, column=0, columnspan=5, sticky="ew", pady=10, ipady=5)
        ttk.Label(
            ac_rh_frame, text="Humidity LCL:"
        ).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.lcl_rh = tk.StringVar(value="")
        self.lcl_rh_entry = ttk.Entry(ac_rh_frame, textvariable=self.lcl_rh, width=10)
        self.lcl_rh_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(
            ac_rh_frame, text="Humidity UCL:"
        ).grid(row=0, column=3, sticky=tk.W, pady=8)
        self.ucl_rh = tk.StringVar(value="")
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

        try:
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
            min_max_data_frame = pd.DataFrame(columns=cols)
            if self.od_enabled_var.get():
                od_frame = analyze_excursions(
                    folder,
                    self.od_start_var.get(),
                    self.od_end_var.get(),
                    int(self.recovery_od.get()),
                    channel="temp_and_rh",
                    temp_min=float(self.lcl_temp.get()) if self.lcl_temp.get() else None,
                    temp_max=float(self.ucl_temp.get()) if self.ucl_temp.get() else None,
                    rh_min=float(self.lcl_rh.get()) if self.lcl_rh.get() else None,
                    rh_max=float(self.ucl_rh.get()) if self.ucl_rh.get() else None,
                )
            if self.pf_enabled_var.get():
                pf_frame = analyze_excursions(
                    folder,
                    self.pf_start_var.get(),
                    self.pf_end_var.get(),
                    int(self.recovery_pf.get()),
                    channel="temp_and_rh",
                    temp_min=float(self.lcl_temp.get()) if self.lcl_temp.get() else None,
                    temp_max=float(self.ucl_temp.get()) if self.ucl_temp.get() else None,
                    rh_min=float(self.lcl_rh.get()) if self.lcl_rh.get() else None,
                    rh_max=float(self.ucl_rh.get()) if self.ucl_rh.get() else None,
                )
            for f in files:
                data_min, data_max, data_avg, data_mkt, rh_min, rh_max, rh_avg = (
                    extract_min_max_avg(
                        f,
                        start_date,
                        end_date,
                        date_mode=date_mode,
                        date_index=date_idx,
                        time_index=time_idx,
                        rows_to_skip=rows_to_skip,
                        temp_idx=temp_idx,
                        rh_idx=rh_idx,
                        has_rh=has_rh,
                    )
                )

                new_row = pd.DataFrame(
                    {
                        "Datalogger": Path(f).stem,
                        "Min Temp [°C]": data_min,
                        "Max Temp [°C]": data_max,
                        "Avg Temp [°C]": data_avg,
                        "MKT": data_mkt,
                        "RH Min [%]": rh_min,
                        "RH Max [%]": rh_max,
                        "RH Avg [%]": rh_avg,
                    },
                    index=[0],
                )
                min_max_data_frame = pd.concat([min_max_data_frame, new_row], ignore_index=True)

            analysis_df = min_max_data_frame.copy()
            analysis_df["MKT"] = pd.to_numeric(analysis_df["MKT"], errors="coerce")

            if not has_rh:
                metrics = (
                    analysis_df.drop(columns=["RH Min [%]", "RH Max [%]", "RH Avg [%]"])
                    .iloc[:, 1:]
                    .agg(["min", "max", "mean"])
                )
            else:
                analysis_df["RH Min [%]"] = pd.to_numeric(analysis_df["RH Min [%]"], errors="coerce")
                analysis_df["RH Max [%]"] = pd.to_numeric(analysis_df["RH Max [%]"], errors="coerce")
                analysis_df["RH Avg [%]"] = pd.to_numeric(analysis_df["RH Avg [%]"], errors="coerce")
                metrics = analysis_df.iloc[:, 1:].agg(["min", "max", "mean"])

            min_max_data_frame = pd.concat([min_max_data_frame, metrics])
            min_max_data_frame.iloc[-3:, 0] = ["Min", "Max", "Avg"]

            save_path = self.save_var.get().strip()
            output_path = save_path if save_path else os.path.join(folder, "min_max_summary.xlsx")

            with pd.ExcelWriter(output_path) as writer:
                min_max_data_frame.to_excel(writer, sheet_name= "Main Study Summary",index=False)
                if od_frame is not None and not od_frame.empty:
                    od_frame.to_excel(writer, sheet_name="Open Door Challenge", index=False)
                if self.pf_enabled_var.get() and not pf_frame.empty:
                    pf_frame.to_excel(writer, sheet_name="Power Failure Challenge", index=False)


            self.status_var.set("Ready")
            messagebox.showinfo("Success", f"Summary saved successfully to:\n{output_path}")

        except Exception as e:
            self.status_var.set("Error Occurred")
            messagebox.showerror("Execution Error", f"An error occurred during processing:\n{str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DataloggerApp(root)
    root.mainloop()