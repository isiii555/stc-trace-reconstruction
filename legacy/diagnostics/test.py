import pandas as pd
df = pd.read_csv(r"out\eventlog_B2_component_timegap_5s.csv", usecols=["case_id"])
sizes = df.groupby("case_id").size().sort_values(ascending=False)
print("Top 10 largest cases:\n", sizes.head(10))
print("\n% single-event cases:", (sizes==1).mean())
