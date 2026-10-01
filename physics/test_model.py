"""Unit tests for the physical model (run: pytest physics/)."""
import math

from physics.model import RoomParams, RoomState, outdoor_temperature, step, ventilation_flow

P = RoomParams(volume_m3=564, area_m2=188, co2_outdoor_ppm=420, co2_gen_m3_per_s_per_person=5.2e-6,
               infiltration_ach=0.2, ach_per_vent_level=1.3, envelope_w_per_k=470,
               thermal_mass_j_per_k=3.4e7, body_heat_w=100, heater_max_w=15000, heater_gain_w_per_k=7500)


def run(minutes, occupants, vent, setpoint, t_out=-10.0, s=None):
    s = s or RoomState(co2_ppm=420, temp_c=21)
    for _ in range(minutes):
        s = step(P, s, occupants, vent, setpoint, t_out, 60)
    return s


def test_co2_rises_with_people_and_falls_with_ventilation():
    full = run(30, occupants=60, vent=0, setpoint=21)
    assert full.co2_ppm > 900, "60 people in a closed lecture room must push CO₂ up within 30 min"
    vented = run(30, occupants=60, vent=3, setpoint=21)
    assert vented.co2_ppm < full.co2_ppm, "the same actuator must lower CO₂"
    empty = run(60, occupants=0, vent=3, setpoint=21, s=full)
    assert empty.co2_ppm < 500, "an empty ventilated room decays back towards outdoor level"


def test_ventilation_costs_heating_energy_in_winter():
    closed = run(60, occupants=20, vent=0, setpoint=21, t_out=-15)
    vented = run(60, occupants=20, vent=3, setpoint=21, t_out=-15)
    assert vented.energy_kwh > closed.energy_kwh, "fresh air at −15 °C must cost heating energy"


def test_heating_is_gradual_and_bounded():
    cold = RoomState(co2_ppm=420, temp_c=15)
    after_5 = run(5, occupants=0, vent=0, setpoint=21, s=cold)
    after_60 = run(60, occupants=0, vent=0, setpoint=21, s=cold)
    assert 15 < after_5.temp_c < after_60.temp_c <= 21.5
    assert after_5.heater_w <= P.heater_max_w


def test_ventilation_flow_monotone():
    assert ventilation_flow(P, 0) < ventilation_flow(P, 1) < ventilation_flow(P, 3)


def test_outdoor_temperature_seasonal():
    assert outdoor_temperature(20, 5) < -5
    assert outdoor_temperature(200, 15) > 10
    assert math.isfinite(outdoor_temperature(1, 0))
