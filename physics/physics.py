import numpy as np
import requests
import pandas as pd 
from scipy.optimize import brentq

crr_values = pd.DataFrame(columns = ["Surface", "Road", "Gravel", "MTB"], data = [["Brick", .0055, .008, .009],
                                                                                  ["Cobbles",.0065, .008, .009],
                                                                                  ["Dirt", .016, .009, .01],
                                                                                  ["Grass", .025, .016, .014],
                                                                                  ["Gravel", .012, .006, .014],
                                                                                  ["Ice/Snow", .0055, .006, .014],
                                                                                  ["Pavement", .004, .008, .009],
                                                                                  ["Sand", .004, .008, .009],
                                                                                  ["Wood", .0065, .008, .009]])

# ---------------------------------------------------------------------------
# Physics constants
# ---------------------------------------------------------------------------
AIR_DENSITY = 1.225        # kg/m^3 at sea level
GRAVITY = 9.8067           # m/s^2
DRIVETRAIN_LOSS = 0.025    # 2.5% drivetrain loss
CRR_DEFAULT = 0.004        # road surface

# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------
def frontal_area_from_rider(height_m, weight_kg):
    """Uses Faria formula
    Returns estimated frontal area in m2."""
    return 0.0293 * (height_m ** 0.725) * (weight_kg ** 0.425) + 0.0604


def get_bike_wheel_data(frame_id, wheel_id, level, bikes_by_key):
    entry = bikes_by_key.get((frame_id, wheel_id))
    if entry is None:
        return None, None
    return entry["weight"][level], entry["cd"][level]


def calc_speed(power_w, gradient, frame_id, wheel_id, level, height_cm, weight_kg,
               bikes_by_key, crr):
    """Returns (speed_kph, CdA, bike_weight_kg) or (None, CdA, bike_weight_kg)
    if no equilibrium speed was found in range."""
    height_m = height_cm / 100
    FA = frontal_area_from_rider(height_m, weight_kg)
    bike_kg, bike_cd = get_bike_wheel_data(frame_id, wheel_id, level, bikes_by_key)
    if bike_kg is None:
        return None, None, None

    total_weight = weight_kg + bike_kg
    CdA = FA * bike_cd

    v = np.linspace(0.1, 30, 30000)
    theta = np.arctan(gradient)
    power_value = power_w * (1 - DRIVETRAIN_LOSS)
    def power_balance(v):
        return (
            power_value
            - (
                v*crr*total_weight*GRAVITY*np.cos(theta)
                + 0.5*AIR_DENSITY*CdA*v**3
                + v*total_weight*GRAVITY*np.sin(theta)
            )
        )
    v_eq = brentq(power_balance, 0.01, 40)
    # resistive = (v * crr * total_weight * GRAVITY * np.cos(theta) +
    #              0.5 * AIR_DENSITY * CdA * v ** 3 +
    #              v * total_weight * GRAVITY * np.sin(theta))
    # diff = power_value - resistive
    # sign_change = np.where(np.diff(np.sign(diff)))[0]
    # if len(sign_change) == 0:
    #     return None, CdA, bike_kg

    # i = sign_change[0]
    # v_eq = np.interp(0, [diff[i], diff[i + 1]], [v[i], v[i + 1]])
    return v_eq * 3.6, CdA, bike_kg

def calc_distance(power_w, gradient, frame_id, wheel_id, level, height_cm, weight_kg, bikes_by_key, crr, time_s):
    """Returns (distance (km), CdA, bike_weight_kg)"""
    v_kph, CdA, bike_kg = calc_speed(power_w, gradient, frame_id, wheel_id, level, height_cm, weight_kg, bikes_by_key, crr)
    distance_km = v_kph*(time_s/(60*60))
    return distance_km, CdA, bike_kg

def calc_time_to_distance(power_w, gradient, frame_id, wheel_id, level, height_cm, weight_kg, bikes_by_key, crr, distance_km):
    """Returns (time (s) to specified distance, CdA, bike_weight_kg)"""
    v_kph, CdA, bike_kg = calc_speed(power_w, gradient, frame_id, wheel_id, level, height_cm, weight_kg, bikes_by_key, crr)
    time_hr = distance_km/v_kph
    return time_hr*(60*60), CdA, bike_kg

