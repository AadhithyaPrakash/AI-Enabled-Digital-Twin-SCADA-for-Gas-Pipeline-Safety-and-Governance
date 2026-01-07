
# Pipeline Physical Parameters

PIPELINE_LENGTH_M = 10_000        # 10 km
PIPELINE_DIAMETER_M = 0.8         # 800 mm
GAS_DENSITY = 0.8                 # kg/m³ (approx)

# Bends modeled as effective length
NUM_BENDS = 6
BEND_EQUIVALENT_LENGTH_FACTOR = 8  # × diameter


# Nominal Operating Conditions

NORMAL_PRESSURE_BAR = 60.0
NORMAL_FLOW_M3S = 25.0
NORMAL_TEMPERATURE_C = 30.0
NORMAL_VIBRATION = 0.4


# SCADA Reference Thresholds

PRESSURE_MIN = 50.0
PRESSURE_MAX = 70.0
FLOW_MIN = 20.0
FLOW_MAX = 30.0


# Simulation Control

TIME_STEP_SECONDS = 1
TOTAL_STEPS = 300

# Physics tuning (simplified)
FRICTION_COEFFICIENT = 0.002
