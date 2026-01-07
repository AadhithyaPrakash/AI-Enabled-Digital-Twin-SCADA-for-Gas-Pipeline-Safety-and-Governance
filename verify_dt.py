import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/raw/dt_pipeline_data.csv")

plt.figure()
plt.plot(df["pressure_bar"], label="Pressure (bar)")
plt.plot(df["flow_m3s"], label="Flow (m3/s)")
plt.legend()
plt.title("Digital Twin Output Verification")
plt.show()
