import pandas as pd
import matplotlib.pyplot as plt
import os

# List of p-values as percentages (to match filenames)
p_values = [0, 20, 40, 60, 80]
dfs = []

for p in p_values:
    filename = f"latency_p{p}.csv"
    if not os.path.exists(filename):
        print(f"[Warning] File not found: {filename}")
        continue
    try:
     
        df = pd.read_csv(filename, on_bad_lines='skip')

        if "latency_seconds" not in df.columns or "operation" not in df.columns:
            print(f"[Warning] Skipping {filename} due to missing columns.")
            continue
        df["p_value"] = p / 100.0  # Normalize p for grouping
        dfs.append(df)
    except Exception as e:
        print(f"[Error] Failed to read {filename}: {e}")

# Combine all valid data
if not dfs:
    print("No valid data found. Exiting.")
    exit()

df_all = pd.concat(dfs)

# Group by p_value and operation, compute average latency
avg_latency = df_all.groupby(["p_value", "operation"])["latency_seconds"].mean().unstack()

# Plot
avg_latency.plot(kind="bar", figsize=(12, 7))
plt.title("Average Latency by Operation Across Trade Probabilities")
plt.ylabel("Latency (seconds)")
plt.xlabel("Trade Probability (p)")
plt.xticks(rotation=0)
plt.grid(True)
plt.tight_layout()
plt.legend(title="operation")
plt.show()
