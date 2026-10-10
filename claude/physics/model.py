"""Per-room physical model: CO₂ mass balance + heat balance. Pure functions → unit-testable.

CO₂ (ppm):   dC/dt = g·n·1e6 / V  −  (Q/V)·(C − C_out)
Temperature: C_th·dT/dt = k_env·(T_out − T) + q_body·n + P_heat − ρ·c_p·Q_inf·(T − T_out) − ρ·c_p·Q_mech·(T − T_sup)

with  Q = Q_inf + Q_mech,  Q_inf = ACH_inf·V/3600,  Q_mech = level·ACH_per_level·V/3600   [m³/s]
      P_heat = clamp(K_heater·(setpoint − T), 0, P_max)          ← the heating actuator (setpoint °C)

Supply air (since 10 Oct): the mechanical ventilation (the vent actuator) delivers air from an air-handling
unit (AHU) at T_sup = `supply_temp_c`; infiltration still enters at outdoor temperature. The AHU first
recovers heat from the exhaust air (efficiency η = `heat_recovery`), then heats the rest up to T_sup:
      P_AHU = ρ·c_p·Q_mech·max(0, T_sup − (T_out + η·(T − T_out)))
P_AHU is counted separately (`ahu_energy_kwh`) so that ventilation is never free. Without `supply_temp_c`
in the config the model behaves as before: all air at outdoor temperature, no AHU.

Deliberately simple (course: "don't spend weeks on physics"). Limitations to state honestly in the
report: perfect mixing, no inter-room air exchange, no solar gain, no humidity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RHO_AIR = 1.2        # kg/m³
CP_AIR = 1005.0      # J/(kg·K)


@dataclass
class RoomParams:
    volume_m3: float
    area_m2: float
    co2_outdoor_ppm: float
    co2_gen_m3_per_s_per_person: float
    infiltration_ach: float
    ach_per_vent_level: float
    envelope_w_per_k: float          # k_env  (= per-m² value × floor area)
    thermal_mass_j_per_k: float      # C_th   (= per-m³ value × volume)
    body_heat_w: float
    heater_max_w: float
    heater_gain_w_per_k: float
    supply_temp_c: float | None = None   # AHU supply-air temperature; None = mechanical air at outdoor temp
    heat_recovery: float = 0.0           # AHU heat-recovery efficiency η (0..1)


@dataclass
class RoomState:
    co2_ppm: float
    temp_c: float
    energy_kwh: float = 0.0          # integrated room-heater energy (evaluation metric)
    heater_w: float = 0.0
    ahu_energy_kwh: float = 0.0      # integrated AHU heating energy for this room's supply air
    ahu_w: float = 0.0


def params_from_config(cfg: dict, area_m2: float, height_m: float) -> RoomParams:
    p = cfg["physics"]
    vol = area_m2 * height_m
    return RoomParams(
        volume_m3=vol,
        area_m2=area_m2,
        co2_outdoor_ppm=p["co2_outdoor_ppm"],
        co2_gen_m3_per_s_per_person=p["co2_gen_m3_per_s_per_person"],
        infiltration_ach=p["infiltration_ach"],
        ach_per_vent_level=p["ach_per_vent_level"],
        envelope_w_per_k=p["envelope_w_per_k_per_m2_floor"] * area_m2,
        thermal_mass_j_per_k=p["thermal_mass_j_per_k_per_m3"] * vol,
        body_heat_w=p["body_heat_w"],
        heater_max_w=p["heater_max_w_per_m2_floor"] * area_m2,
        heater_gain_w_per_k=p["heater_gain_w_per_k_per_m2_floor"] * area_m2,
        supply_temp_c=p.get("supply_temp_c"),
        heat_recovery=float(p.get("heat_recovery", 0.0)),
    )


def ventilation_flow(p: RoomParams, vent_level: float) -> float:
    """Fresh-air flow in m³/s for a damper/fan level (0..3, fractional while travelling)."""
    ach = p.infiltration_ach + max(0.0, vent_level) * p.ach_per_vent_level
    return ach * p.volume_m3 / 3600.0


def heater_power(p: RoomParams, temp_c: float, setpoint_c: float) -> float:
    """Proportional radiator: full power when far below setpoint, zero above it."""
    return min(p.heater_max_w, max(0.0, p.heater_gain_w_per_k * (setpoint_c - temp_c)))


def step(p: RoomParams, s: RoomState, occupants: int, vent_level: float, setpoint_c: float,
         t_out_c: float, dt_s: float, max_substep_s: float = 30.0) -> RoomState:
    """Advance one room by dt_s simulated seconds (explicit Euler, sub-stepped for stability)."""
    n_sub = max(1, int(math.ceil(dt_s / max_substep_s)))
    h = dt_s / n_sub
    co2, temp, energy, ahu_energy = s.co2_ppm, s.temp_c, s.energy_kwh, s.ahu_energy_kwh
    q = ventilation_flow(p, vent_level)
    q_inf = p.infiltration_ach * p.volume_m3 / 3600.0
    q_mech = q - q_inf
    heater = ahu = 0.0
    for _ in range(n_sub):
        # CO₂ mass balance (all fresh air is outdoor air, whatever its temperature)
        gen_ppm_per_s = p.co2_gen_m3_per_s_per_person * occupants * 1e6 / p.volume_m3
        co2 += h * (gen_ppm_per_s - (q / p.volume_m3) * (co2 - p.co2_outdoor_ppm))
        # heat balance
        heater = heater_power(p, temp, setpoint_c)
        loss_env = p.envelope_w_per_k * (t_out_c - temp)
        if p.supply_temp_c is None:
            loss_vent = RHO_AIR * CP_AIR * q * (temp - t_out_c)
            ahu = 0.0
        else:
            loss_vent = RHO_AIR * CP_AIR * (q_inf * (temp - t_out_c) + q_mech * (temp - p.supply_temp_c))
            after_recovery = t_out_c + p.heat_recovery * (temp - t_out_c)
            ahu = RHO_AIR * CP_AIR * q_mech * max(0.0, p.supply_temp_c - after_recovery)
        dT = (loss_env + p.body_heat_w * occupants + heater - loss_vent) / p.thermal_mass_j_per_k
        temp += h * dT
        energy += heater * h / 3.6e6
        ahu_energy += ahu * h / 3.6e6
    return RoomState(co2_ppm=max(p.co2_outdoor_ppm, co2), temp_c=temp, energy_kwh=energy, heater_w=heater,
                     ahu_energy_kwh=ahu_energy, ahu_w=ahu)


def outdoor_temperature(day_of_year: int, hour: float, annual_mean_c: float = 2.0,
                        annual_amplitude_c: float = 13.0, daily_amplitude_c: float = 4.0,
                        coldest_day_of_year: int = 20) -> float:
    """Luleå-ish outdoor temperature: annual cosine (min ≈ −11 °C in January, max ≈ +15 °C in July)
    plus a daily swing with its minimum around 05:00 and maximum around 15:00."""
    annual = annual_mean_c - annual_amplitude_c * math.cos(2 * math.pi * (day_of_year - coldest_day_of_year) / 365.0)
    daily = -daily_amplitude_c * math.cos(2 * math.pi * (hour - 15.0) / 24.0)
    return annual + daily
