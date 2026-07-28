import os
import glob
import pandas as pd


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

    records = []
    if channel in ("temp", "temp_and_rh"):
        for r in extract(df, temp_col, temp_min, temp_max):
            records.append({"Logger": logger_number, "Parameter": "Temperature", **r})
    if channel in ("rh", "temp_and_rh"):
        for r in extract(df, rh_col, rh_min, rh_max):
            records.append({"Logger": logger_number, "Parameter": "RH", **r})
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


if __name__ == "__main__":
    analyze_excursions(
        directory=r"g:\work\Thermal Mapping\4027\5th_try",
        challenge_start="2026-07-16 04:24:51 PM",
        challenge_end="2026-07-26 03:34:51 PM",
        allowed_recovery=30,
        channel="temp_and_rh",
        temp_min=30, temp_max=35,
        rh_min=35, rh_max=65
    )
