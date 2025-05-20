import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import requests
from datetime import date

st.markdown("""
    <head>
        <meta property="og:image" content="https://iqsolar.streamlit.app/?/logo.png">
        <meta property="og:title" content="SolarIQ>
        <meta property="og:description" content="Estimate solar performance and carbon impact by location.">
    </head>
""", unsafe_allow_html=True)


#api keys
API_KEY_NREL = st.secrets["API_KEY_NREL"]
API_KEY_TOMORROW = st.secrets["API_KEY_TOMORROW"]


#location lookup
def get_coordinates_from_city(city_name):
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city_name + ", USA", "format": "json", "limit": 1},
            headers={"User-Agent": "solar-calculator-app"}
        )
        response.raise_for_status()
        data = response.json()
        if data:
            return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
        else:
            return None
    except Exception as e:
        return None


#daily irradiance
@st.cache_data
def fetch_daily_irradiance(location):
    coords = get_coordinates_from_city(location)
    if not coords:
        return None
    url = f"https://developer.nrel.gov/api/solar/solar_resource/v1.json?api_key={API_KEY_NREL}&lat={coords['lat']}&lon={coords['lon']}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            data = response.json()
            ghi = data["outputs"]["avg_ghi"]["annual"]
            return ghi  # in kWh/m²/day
        except:
            return None
    else:
        return None

#temperature data
@st.cache_data
def fetch_tomorrow_temperature(location):
    coords = get_coordinates_from_city(location)
    url = f"https://api.tomorrow.io/v4/weather/forecast?location={coords['lat']},{coords['lon']}&apikey={API_KEY_TOMORROW}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        try:
            return float(data["timelines"]["hourly"][0]["values"]["temperature"])
        except:
            return 25
    return 25

#efficiency calculator
class SolarCellCalculator:
    def __init__(self, efficiency, area_m2, tilt_angle):
        self.efficiency = efficiency
        self.area_m2 = area_m2
        self.tilt_angle = tilt_angle

    def calculate_daily_production(self, daily_irradiance_kwh, temperature_C):
        # Convert to Wh
        daily_irradiance_wh = daily_irradiance_kwh * 1000

        # Apply temperature and tilt
        temp_factor = 1 - 0.004 * max(0, temperature_C - 25)
        tilt_factor = np.sin(np.radians(self.tilt_angle)) * 0.5 + 0.5

        # Simulate hourly profile (Gaussian centered at noon)
        profile = np.exp(-0.5 * ((np.arange(24) - 12)/4)**2)
        profile /= profile.sum()
        hourly_irradiance = daily_irradiance_wh * profile  # Wh/m² each hour

        # Calculate hourly production
        hourly_production = [
            irr * self.area_m2 * self.efficiency * temp_factor * tilt_factor
            for irr in hourly_irradiance
        ]
        total_production = sum(hourly_production)
        return {
            'hourly_production': hourly_production,
            'total_production': total_production
        }

#summary generation
def summarize_output(location, daily_kwh, annual_kwh, rate_per_kwh=0.15):
    # Classify system size
    if annual_kwh >= 8000:
        system_size = "a large-scale residential or small commercial setup"
        benefit = "significant energy savings and potential sell-back to the grid"
    elif annual_kwh >= 4000:
        system_size = "a standard home solar system"
        benefit = "a strong offset to your household electricity use"
    else:
        system_size = "a small or supplemental system"
        benefit = "a modest contribution toward reducing energy costs"

    # Calculate estimated savings
    daily_savings = daily_kwh * rate_per_kwh
    annual_savings = annual_kwh * rate_per_kwh

    # Return plain-text summary (no markdown, no italics)
    summary = (
        f"Location: {location}\n"
        f"Estimated Production: {daily_kwh:.2f} kWh/day | {annual_kwh:.2f} kWh/year\n"
        f"System Type: {system_size}\n"
        f"Benefits: {benefit}.\n"
        f"Estimated Savings: ${daily_savings:.2f} per day, or approximately ${annual_savings:.2f} per year.\n\n"
        f"To maximize your system's performance, ensure the panels are installed with optimal tilt, "
        f"kept clean, and inspected regularly."
    )

    return summary


#streamlit
st.set_page_config(page_title="SolarIQ", layout="wide")
st.title("SolarIQ")
st.subheader("Know what solar can do for you before you invest.")
st.sidebar.image("logo.png", use_container_width=True)
tab1, tab2, tab3 = st.tabs(["📈 Solar Performance", "📐 Solar Sizing Tool","🌍 Environmental Impact"])

with tab1:
    st.sidebar.header("Solar Panel Inputs")
    location = st.text_input("City of Residence:")

    if location:
        coords = get_coordinates_from_city(location)
        if not coords:
            st.error("No matching city found. Please enter a valid U.S. city name.")
            st.stop()

    efficiency = st.sidebar.slider("Cell Efficiency (%)", 5, 30, 20, key = "efficiency_main") / 100
    area = st.sidebar.number_input("Panel Area (m²)", min_value=0.1, value=2.0, step=0.1)
    tilt = st.sidebar.slider("Tilt Angle (degrees)", 0, 90, 30, key = "tilt_main")

    if location:
        ghi_daily = fetch_daily_irradiance(location)
        temperature = fetch_tomorrow_temperature(location)

        if ghi_daily is None:
            st.error("Failed to retrieve irradiance data.")
            st.stop()

        calculator = SolarCellCalculator(efficiency, area, tilt)
        result = calculator.calculate_daily_production(ghi_daily, temperature)

        daily_kwh = result['total_production'] / 1000
        annual_kwh = daily_kwh * 365

        #Quick one-line evaluation
        if annual_kwh >= 3000:
            st.success("👍 Based on your data, solar investment looks highly beneficial.")
        elif annual_kwh >= 900:
            st.info("⚠️ Solar could be worth it—depends on local electricity rates and usage.")
        else:
            st.warning("👎 Solar may offer limited savings at this location with current solar panel technology.")

        #Optional detailed analysis
        if st.checkbox("Show detailed performance evaluation"):
            evaluation = summarize_output(location, daily_kwh, annual_kwh)
            st.text(evaluation)

        

        st.header("Energy Production in Kilowatt Hour")
        st.metric("Total Daily Production", f"{result['total_production']:.2f} Wh", f"{result['total_production'] / 1000:.2f} kWh")
        daily_kwh = result['total_production'] / 1000
        annual_kwh = daily_kwh * 365
        st.metric("Estimated Annual Production", f"{annual_kwh:.2f} kWh")


        fig, ax = plt.subplots(figsize=(7, 3.5))
        hours = range(24)
        ax.plot(hours, result['hourly_production'], label="Hourly Production", color='green')
        ax.fill_between(hours, result['hourly_production'], color='green', alpha=0.3)
        ax.set_xlabel("Hour")
        ax.set_ylabel("Energy (Wh)")
        ax.set_title(f"Simulated Hourly Solar Production\n{location} | Temp: {temperature}°C")
        ax.grid(True)
        st.pyplot(fig)

with tab2:
    st.header("📐 Solar Sizing Tool")
    st.markdown("Estimate the ideal solar panel size based on your electricity usage goals.")

    st.sidebar.header("Sizing Inputs")
    location_sizing = st.text_input("City for Sizing:", key="sizing_location")

    if location_sizing:
        coords = get_coordinates_from_city(location_sizing)
        if not coords:
            st.error("No matching city found. Please enter a valid U.S. city name.")
            st.stop()

        ghi_daily = fetch_daily_irradiance(location_sizing)
        temperature = fetch_tomorrow_temperature(location_sizing)

        if ghi_daily is None:
            st.error("Failed to retrieve irradiance data.")
            st.stop()

        st.sidebar.markdown("#### Panel & Usage Preferences")
        efficiency = st.sidebar.slider("Cell Efficiency (%)", 5, 30, 20, key="eff_sizing") / 100
        tilt = st.sidebar.slider("Tilt Angle (degrees)", 0, 90, 30, key="tilt_sizing")
        monthly_usage = st.sidebar.number_input("Monthly Electricity Use (kWh)", min_value=50, value=900, step=50, key="usage_sizing")
        offset_target = st.sidebar.slider("Offset Target (%)", min_value=10, max_value=100, value=80, key="offset_sizing")

        target_annual_kwh = monthly_usage * 12 * (offset_target / 100)

        calculator_temp = SolarCellCalculator(efficiency=1, area_m2=1, tilt_angle=tilt)
        base_output_per_m2 = calculator_temp.calculate_daily_production(ghi_daily, temperature)['total_production'] / 1000 * 365

        if base_output_per_m2 == 0:
            st.error("Irradiance data returned 0. Cannot size the system.")
            st.stop()

        required_area = target_annual_kwh / base_output_per_m2

        # Display results
        st.subheader(f"Results for **{location_sizing.title()}**")
        st.markdown(f"-  **Target Annual Usage Offset**: `{target_annual_kwh:.0f} kWh/year`")
        st.markdown(f"-  **Estimated Panel Area Needed**: `{required_area:.2f} m²`")
        st.markdown(f"-  **System Efficiency**: `{efficiency*100:.0f}%` @ `{tilt}°` tilt")
        st.markdown(f"-  **Weather-Based Estimate** at {temperature:.1f}°C")

        st.info("This is a sizing estimate. Actual installation may vary based on roof shape, shading, and system losses.")
with tab3:
    st.header("🌱 Environmental Impact")

    location_env = st.text_input("City Name:", key="env_location")

    if location_env:
        coords = get_coordinates_from_city(location_env)
        if not coords:
            st.error("No matching city found. Please enter a valid U.S. city name.")
            st.stop()

        ghi_daily = fetch_daily_irradiance(location_env)
        if ghi_daily is None:
            st.error("Failed to retrieve irradiance data.")
            st.stop()

        temperature = fetch_tomorrow_temperature(location_env)

        efficiency = st.slider("Cell Efficiency (%)", 5, 30, 20, key="env_eff") / 100
        area = st.number_input("Panel Area (m²)", min_value=0.1, value=2.0, step=0.1, key="env_area")
        tilt = st.slider("Tilt Angle (degrees)", 0, 90, 30, key="env_tilt")

        calculator = SolarCellCalculator(efficiency, area, tilt)
        result = calculator.calculate_daily_production(ghi_daily, temperature)

        daily_kwh = result['total_production'] / 1000
        annual_kwh = daily_kwh * 365

        emissions_factor = 0.4  # kg CO₂ per kWh
        co2_saved_kg = annual_kwh * emissions_factor
        trees_planted = co2_saved_kg / 21.77
        cars_removed = co2_saved_kg / 4600

        st.markdown(f"**Estimated Annual CO₂ Offset:** `{co2_saved_kg:,.0f} kg`")
        st.markdown(f"- 🌳 Equivalent to planting **{trees_planted:.0f} trees/year**")
        st.markdown(f"- 🚗 Equivalent to removing **{cars_removed:.2f} cars** from the road")


