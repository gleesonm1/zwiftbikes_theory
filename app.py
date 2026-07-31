import streamlit as st
import numpy as np
import requests

st.set_page_config(page_title="Zwift Bike Speed Calculator", layout="wide")

# ---------------------------------------------------------------------------
# Physics constants (same as your original script)
# ---------------------------------------------------------------------------
AIR_DENSITY = 1.225        # kg/m^3 at sea level
GRAVITY = 9.8067           # m/s^2
DRIVETRAIN_LOSS = 0.025    # 2.5% drivetrain loss
CRR_DEFAULT = 0.004        # road surface

# Standard baseline bike used for "time saved vs stock" comparisons,
# matching calc_time_diff_to_standard from your original script
STANDARD_FRAME_ID = "F088"   # Zwift Carbon
STANDARD_WHEEL_ID = "W035"   # 32mm Carbon
STANDARD_LEVEL = 0

LEVEL_LABELS = ["Level 0", "Level 1", "Level 2", "Level 3", "Level 4", "Level 5 (Max)"]


# ---------------------------------------------------------------------------
# Data loading (cached so we don't re-hit zwifterbikes.web.app every rerun)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_data():
    r = requests.get("https://zwifterbikes.web.app/assets/frames.json")
    r.encoding = "utf-8-sig"
    frames = r.json()

    r = requests.get("https://zwifterbikes.web.app/assets/wheels.json")
    r.encoding = "utf-8-sig"
    wheels = r.json()

    r = requests.get("https://zwifterbikes.web.app/assets/bikes.json")
    r.encoding = "utf-8-sig"
    bikes = r.json()

    return frames, wheels, bikes


# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------
def frontal_area_from_rider(height_m, weight_kg):
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

    v = np.linspace(0.1, 30, 3000)
    theta = np.arctan(gradient)
    power_value = power_w * (1 - DRIVETRAIN_LOSS)
    resistive = (v * crr * total_weight * GRAVITY * np.cos(theta) +
                 0.5 * AIR_DENSITY * CdA * v ** 3 +
                 v * total_weight * GRAVITY * np.sin(theta))
    diff = power_value - resistive
    sign_change = np.where(np.diff(np.sign(diff)))[0]
    if len(sign_change) == 0:
        return None, CdA, bike_kg

    i = sign_change[0]
    v_eq = np.interp(0, [diff[i], diff[i + 1]], [v[i], v[i + 1]])
    return v_eq * 3.6, CdA, bike_kg


# ---------------------------------------------------------------------------
# Load data + build lookup structures
# ---------------------------------------------------------------------------
frames, wheels, bikes = load_data()

# frameid -> full frame record, wheelid -> full wheel record
frames_by_id = {f["frameid"]: f for f in frames}
wheels_by_id = {w["wheelid"]: w for w in wheels}
bikes_by_key = {(b["frameid"], b["wheelid"]): b for b in bikes}

# Display labels replicate the original UI's "Make Model (A:x W:x)" format
frame_label = lambda f: f"{f['framemake']} {f['framemodel']} (A:{f['frameaero']} W:{f['frameweight']})"
wheel_label = lambda w: f"{w['wheelmake']} {w['wheelmodel']} (A:{w['wheelaero']} W:{w['wheelweight']})"

frame_options = {frame_label(f): f["frameid"] for f in frames}
frame_names_sorted = sorted(frame_options.keys())


def wheel_options_for_frame(frame_id):
    """Only show wheels that (a) actually have a bikes.json entry for this
    frame, and (b) fit the frame's type (Standard/TT/Gravel/etc)."""
    frame = frames_by_id[frame_id]
    if frame["framewheeltype"] == "fixed":
        return {}
    valid = {}
    for w in wheels:
        fits = [t.strip() for t in w["wheelfitsframe"].split(",")]
        if frame["frametype"] not in fits:
            continue
        if (frame_id, w["wheelid"]) not in bikes_by_key:
            continue
        valid[wheel_label(w)] = w["wheelid"]
    return valid


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("🚴 Zwift Bike Speed Calculator")
st.caption("Speed solved from the steady-state power balance: rolling resistance + aero drag + gravity.")

top1, top2, top3 = st.columns(3)
with top1:
    power = st.slider("Power (W)", 100, 500, 250, step=5)
with top2:
    gradient_pct = st.slider("Gradient (%)", -10.0, 15.0, 0.0, step=0.5)
with top3:
    crr = st.number_input("Crr", min_value=0.001, max_value=0.010, value=CRR_DEFAULT, step=0.0005, format="%.4f")

gradient = gradient_pct / 100.0


def bike_panel(col, label, key_prefix, default_frame_id, default_wheel_id):
    with col:
        st.subheader(label)

        frame_name = st.selectbox(
            "Frame", frame_names_sorted,
            index=frame_names_sorted.index(frame_label(frames_by_id[default_frame_id])),
            key=f"{key_prefix}_frame",
        )
        frame_id = frame_options[frame_name]
        frame = frames_by_id[frame_id]

        wopts = wheel_options_for_frame(frame_id)
        if not wopts:
            st.info("This frame has fixed wheels — no wheel selection needed.")
            wheel_id = ""
        else:
            wheel_names_sorted = sorted(wopts.keys())
            default_wheel_name = wheel_label(wheels_by_id[default_wheel_id]) if default_wheel_id in wheels_by_id else None
            default_idx = wheel_names_sorted.index(default_wheel_name) if default_wheel_name in wheel_names_sorted else 0
            wheel_name = st.selectbox("Wheels", wheel_names_sorted, index=default_idx, key=f"{key_prefix}_wheel")
            wheel_id = wopts[wheel_name]

        level_label = st.selectbox("Upgrade Level", LEVEL_LABELS, index=5, key=f"{key_prefix}_level")
        level = LEVEL_LABELS.index(level_label)

        c1, c2 = st.columns(2)
        with c1:
            height = st.number_input("Height (cm)", 140, 210, 175, key=f"{key_prefix}_height")
        with c2:
            weight = st.number_input("Weight (kg)", 40, 120, 75, key=f"{key_prefix}_weight")

        return frame_id, wheel_id, level, height, weight


col1, col2 = st.columns(2)
frame1, wheel1, level1, h1, w1 = bike_panel(
    col1, "Setup A", "a", "F086", "W057"  # Zwift Aero + ENVE SES 4.5 PRO
)
frame2, wheel2, level2, h2, w2 = bike_panel(
    col2, "Setup B", "b", "F061", "W066"  # Specialized Aethos + Princeton Wake 6560 Lava
)

speed1, cda1, bw1 = calc_speed(power, gradient, frame1, wheel1, level1, h1, w1, bikes_by_key, crr)
speed2, cda2, bw2 = calc_speed(power, gradient, frame2, wheel2, level2, h2, w2, bikes_by_key, crr)

std_speed1, _, _ = calc_speed(power, gradient, STANDARD_FRAME_ID, STANDARD_WHEEL_ID, STANDARD_LEVEL, h1, w1, bikes_by_key, crr)
std_speed2, _, _ = calc_speed(power, gradient, STANDARD_FRAME_ID, STANDARD_WHEEL_ID, STANDARD_LEVEL, h2, w2, bikes_by_key, crr)

st.divider()
res1, res2 = st.columns(2)

with res1:
    if speed1 is not None:
        st.metric("Speed — Setup A", f"{speed1:.2f} km/h")
        st.caption(f"CdA: {cda1:.4f} m² · Bike weight: {bw1:.2f} kg")
        if std_speed1:
            secs_per_km = 3600 * (1 / speed1 - 1 / std_speed1)
            st.caption(f"{'−' if secs_per_km < 0 else '+'}{abs(secs_per_km):.1f} sec/km vs stock Zwift Carbon")
    else:
        st.error("No equilibrium speed found for Setup A in this power/gradient range.")

with res2:
    if speed2 is not None:
        st.metric("Speed — Setup B", f"{speed2:.2f} km/h")
        st.caption(f"CdA: {cda2:.4f} m² · Bike weight: {bw2:.2f} kg")
        if std_speed2:
            secs_per_km = 3600 * (1 / speed2 - 1 / std_speed2)
            st.caption(f"{'−' if secs_per_km < 0 else '+'}{abs(secs_per_km):.1f} sec/km vs stock Zwift Carbon")
    else:
        st.error("No equilibrium speed found for Setup B in this power/gradient range.")

if speed1 is not None and speed2 is not None:
    st.divider()
    diff = speed2 - speed1
    if abs(diff) < 0.005:
        st.info("Setup A and Setup B are essentially identical at this power and gradient.")
    elif diff > 0:
        st.success(f"Setup B is **{diff:.2f} km/h faster** than Setup A at {power}W on a {gradient_pct:.1f}% grade.")
    else:
        st.success(f"Setup A is **{abs(diff):.2f} km/h faster** than Setup B at {power}W on a {gradient_pct:.1f}% grade.")