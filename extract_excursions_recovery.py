import os
from tkinter import messagebox 
import pandas as pd
from datetime import datetime, timedelta

"""
@ This script takes a dataframe of readings and analyzes excursions based on user-defined parameters.
@ It identifies excursions that occur within a specified challenge window and calculates the time taken for readings to recover to within the defined acceptable range.
@ The result is output as a dataframe containing details of each excursion, including start and end times, readings, recovery times, and pass/fail status based on the recovery time limit.
@ Inputs: Dataframe, Time column index, Value column index, Min value, Max value, Challenge start time, Challenge end time, Recovery time limit (in minutes)
"""

def analyze_excursions(
    directory: str,
    time_col_idx: int,
    val_col_idx: int,
    min_val: float,
    max_val: float,
    challenge_start: str,
    challenge_end: str,
    recovery_time_minutes: float
):
    """
    Scans Excel/CSV files for temperature excursions, records reading values
    at the start and end of each excursion, and calculates recovery times.
    """
    
    start_time = pd.to_datetime(challenge_start)
    end_time = pd.to_datetime(challenge_end)
    recovery_limit = pd.Timedelta(minutes=recovery_time_minutes)
    
    # Extend monitoring window to assess post-challenge recovery
    max_monitoring_time = end_time + recovery_limit
    
    valid_extensions = ('.csv', '.xls', '.xlsx')
    all_results = []
    dt_format = '%d-%m-%Y %I:%M:%S %p'

    for filename in os.listdir(directory):
        if not filename.lower().endswith(valid_extensions):
            continue
            
        filepath = os.path.join(directory, filename)
        
        try:
            if filename.lower().endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
                
            time_col_name = df.columns[time_col_idx]
            val_col_name = df.columns[val_col_idx]
            filename = filename.replace('.csv', '').replace('.xls', '').replace('.xlsx', '').replace('.','')
            # Parse dates and numerical data
            df[time_col_name] = pd.to_datetime(df[time_col_name], errors='coerce', format='mixed')
            df[val_col_name] = pd.to_numeric(df[val_col_name], errors='coerce')
            df = df.dropna(subset=[time_col_name, val_col_name])
            
            # Filter data to the monitoring window
            mask = (df[time_col_name] >= start_time) & (df[time_col_name] <= max_monitoring_time)
            analysis_df = df.loc[mask].sort_values(by=time_col_name)
            
            in_excursion = False
            excursion_start = None
            excursion_start_val = None
            excursion_count = 0
            
            for _, row in analysis_df.iterrows():
                current_time = row[time_col_name]
                current_val = row[val_col_name]
                
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
                    recovery_mins = round(recovery_duration.total_seconds() / 60.0, 2)
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
                    
            # Handle excursions that never recovered within the allowed time
            if in_excursion:
                all_results.append({
                    "File": filename,
                    "Excursion #": excursion_count,
                    "Excursion Start": excursion_start.strftime(dt_format),
                    "Start Reading": excursion_start_val,
                    "Excursion End": "N/A",
                    "End Reading": "N/A",
                    "Time to Recover (Minutes)": "Did not recover",
                    "Time to Recover (Formatted)": "N/A",
                    "Pass/Fail": f"FAIL (Did not recover in {recovery_time_minutes} mins)"
                })
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process file {filename}.\nError: {str(e)}")

    results_df = pd.DataFrame(all_results)
    
    print(f"\n--- Analysis Complete. Found {len(all_results)} total excursion events ---")
    if not results_df.empty:
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
    return results_df

def analyze_excursions_df_v2(
    df: pd.DataFrame,
    time_col_idx: int,
    val_col_idx: int,
    min_val: float,
    max_val: float,
    challenge_start,
    challenge_end,
    recovery_limit: pd.Timedelta,
    label: str,
    date_time_format: str = '%d-%m-%Y %I:%M:%S %p',
    date_col_idx: int = 0,
    date_time_separate: bool = False
) -> pd.DataFrame:  
    all_results = []
    dt_format = '%d-%m-%Y %I:%M:%S %p'
    
    # Handle separate Date and Time columns if requested
    if date_time_separate:
        df['DateTime'] = pd.to_datetime(
            df.iloc[:, date_col_idx].astype(str) + ' ' + df.iloc[:, time_col_idx].astype(str),
            errors='coerce'
        )
        time_col_name = 'DateTime'
    else:
        time_col_name = df.columns[time_col_idx]

    val_col_name = df.columns[val_col_idx]
    
    # Standardize inputs to Timestamp/Timedelta
    start_time = pd.to_datetime(challenge_start)
    end_time = pd.to_datetime(challenge_end)
    max_monitoring_time = end_time + recovery_limit

    clean_filename = os.path.splitext(label)[0]

    # Parse dates and numerical data
    df[time_col_name] = pd.to_datetime(df[time_col_name], errors='coerce', format='mixed')
    df[val_col_name] = pd.to_numeric(df[val_col_name], errors='coerce')
    df = df.dropna(subset=[time_col_name, val_col_name])
    
    # Filter data to the monitoring window
    mask = (df[time_col_name] >= start_time) & (df[time_col_name] <= max_monitoring_time)
    analysis_df = df.loc[mask].sort_values(by=time_col_name)
    
    in_excursion = False
    excursion_start = None
    excursion_start_val = None
    excursion_count = 0
    
    for _, row in analysis_df.iterrows():
        current_time = row[time_col_name]
        current_val = row[val_col_name]
        
        is_out_of_bounds = (current_val < min_val) or (current_val > max_val)
        
        if not in_excursion:
            if is_out_of_bounds and (current_time <= end_time):
                in_excursion = True
                excursion_start = current_time
                excursion_start_val = current_val
                excursion_count += 1
                
        elif in_excursion and not is_out_of_bounds:
            in_excursion = False
            recovery_duration = current_time - excursion_start
            recovery_mins = round(recovery_duration.total_seconds() / 60.0, 2)
            recovered_in_time = recovery_duration <= recovery_limit
            
            all_results.append({
                "File": clean_filename,
                "Excursion #": excursion_count,
                "Excursion Start": excursion_start.strftime(dt_format),
                "Start Reading": excursion_start_val,
                "Excursion End": current_time.strftime(dt_format),
                "End Reading": current_val,
                "Time to Recover (Minutes)": recovery_mins,
                "Time to Recover (Formatted)": str(recovery_duration),
                "Pass/Fail": "PASS" if recovered_in_time else "FAIL (Exceeded Limit)"
            })
            
    if in_excursion:
        all_results.append({
            "File": clean_filename,
            "Excursion #": excursion_count,
            "Excursion Start": excursion_start.strftime(dt_format),
            "Start Reading": excursion_start_val,
            "Excursion End": "N/A",
            "End Reading": "N/A",
            "Time to Recover (Minutes)": "Did not recover",
            "Time to Recover (Formatted)": "N/A",
            "Pass/Fail": f"FAIL (Did not recover within allowed time)"
        })

    return pd.DataFrame(all_results)


def analyze_excursions_v2(
    directory: str,
    time_col_idx: int,
    val_col_idx: int,
    min_val: float,
    max_val: float,
    challenge_start: str,
    challenge_end: str,
    recovery_time_minutes: float
) -> pd.DataFrame:
    start_time = pd.to_datetime(challenge_start)
    end_time = pd.to_datetime(challenge_end)
    recovery_limit = pd.Timedelta(minutes=recovery_time_minutes)
      
    valid_extensions = ('.csv', '.xls', '.xlsx')
    all_dfs = []

    for filename in os.listdir(directory):
        if not filename.lower().endswith(valid_extensions):
            continue

        filepath = os.path.join(directory, filename)

        if filename.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df_results = analyze_excursions_df_v2(
            df=df,
            time_col_idx=time_col_idx,
            val_col_idx=val_col_idx,
            min_val=min_val,
            max_val=max_val,
            challenge_start=start_time,
            challenge_end=end_time,
            recovery_limit=recovery_limit,
            label=filename
        )

        if df_results is not None and not df_results.empty:
            all_dfs.append(df_results)

    if all_dfs:
        results_df = pd.concat(all_dfs, ignore_index=True)
    else:
        results_df = pd.DataFrame()

    return results_df
# --- Example Usage ---
if __name__ == "__main__":
    results_df_v1 = analyze_excursions(
        directory="U:\\Qualification\\Drive\\Thermal_Mapping\\QC01\\2026\\QC01-4105\\TM-QC01-4105 30 +-2 -60+-5\\XLS", 
        time_col_idx=1,            # 1 = Date/time column
        val_col_idx=3,             # 3 = Humidity column
        min_val=60.0, 
        max_val=70.0, 
        challenge_start="08/30/2026 10:25:00 AM", 
        challenge_end="08/30/2026 10:40:00 AM",   
        recovery_time_minutes=60.0
    )
    results_df_v2 = analyze_excursions_v2(
        directory="U:\\Qualification\\Drive\\Thermal_Mapping\\QC01\\2026\\QC01-4105\\TM-QC01-4105 30 +-2 -60+-5\\XLS",
        time_col_idx=1,
        val_col_idx=3,
        min_val=60.0,
        max_val=70.0,
        challenge_start="08/30/2026 10:25:00 AM",
        challenge_end="08/30/2026 10:40:00 AM",
        recovery_time_minutes=60.0
    )
    results_df_v2.to_excel(os.path.join("C:\\Users\\ahmed.magdyy\\Desktop","pf_excursion_analysis_results_v2.xlsx"), index=False)
    results_df_v1.to_excel(os.path.join("C:\\Users\\ahmed.magdyy\\Desktop","pf_excursion_analysis_results_v1.xlsx"), index=False)  