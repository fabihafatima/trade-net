import pandas as pd
import matplotlib.pyplot as plt


'''code to Compare the latency of caching and no caching data
   for different p values
'''
cache_files = [(f"cache-output-ec2/latency_p{p}.csv", p/100.0) for p in [0, 20, 40, 60, 80]]
nocache_files = [(f"nocache-output-ec2/latency_p{p}.csv", p/100.0) for p in [0, 20, 40, 60, 80]]

def load_and_label(files, cache_status):
    dfs = []
    for file, p in files:
        df = pd.read_csv(file, on_bad_lines="skip")
        df["p_value"] = p
        df["cache"] = cache_status
        dfs.append(df)
    return pd.concat(dfs)

df_cache = load_and_label(cache_files, "caching")
df_nocache = load_and_label(nocache_files, "no caching")
df_all = pd.concat([df_cache, df_nocache])

# Calculate mean latency per operation, p, and cache
avg = df_all.groupby(["p_value", "operation", "cache"])["latency_seconds"].mean().reset_index()

# Pivot data for easier plotting
pivot_query = avg[avg["operation"] == "lookup"].pivot(index="p_value", columns="cache", values="latency_seconds")
pivot_trade = avg[avg["operation"] == "trade"].pivot(index="p_value", columns="cache", values="latency_seconds")

# Plotting
plt.figure(figsize=(8, 6))

# Query
plt.plot(pivot_query.index, pivot_query["caching"], '-o', label="query (caching)", color="deepskyblue")
plt.plot(pivot_query.index, pivot_query["no caching"], '-o', label="query (no caching)", color="purple")

# Trade
plt.plot(pivot_trade.index, pivot_trade["caching"], '-o', label="buy (caching)", color="red")
plt.plot(pivot_trade.index, pivot_trade["no caching"], '-o', label="buy (no caching)", color="mediumseagreen")

plt.title("Probability vs Latencies")
plt.xlabel("P (Probability of Request)")
plt.ylabel("Latency (seconds)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
