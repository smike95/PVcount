import streamlit as st
import pandas as pd
import pvlib
import plotly.express as px

# Налаштування сторінки
st.set_page_config(page_title="PV Generator Analogue", layout="wide")

st.title("☀️ Спрощений аналог PVsyst (Streamlit)")
st.write("Моделювання фотовольтаїчної системи на основі даних PVGIS та pvlib")

# Sidebar — Вхідні дані
st.sidebar.header("1. Локація та Орієнтація")
coords_input = st.sidebar.text_input("Координати з Google Maps (Широта, Довгота)", "50.4501, 30.5234")

try:
    lat_str, lon_str = coords_input.split(",")
    latitude = float(lat_str.strip())
    longitude = float(lon_str.strip())
except Exception:
    st.sidebar.error("Будь ласка, введіть координати у форматі: `Широта, Довгота`")
    latitude, longitude = 50.4501, 30.5234

tilt = st.sidebar.number_input("Кут нахилу панелей (°)", min_value=0, max_value=90, value=30)
azimuth = st.sidebar.number_input("Азимут (180° = Південь)", min_value=0, max_value=360, value=180)

st.sidebar.header("2. Обладнання")
mode = st.sidebar.radio("Спосіб вибору обладнання:", ["Вручную", "З бібліотеки (SAM)"])

system_capacity_kw = 10.0
system_loss = 0.14

if mode == "Вручную":
    panel_power_w = st.sidebar.number_input("Потужність однієї панелі (Вт)", value=450)
    panel_count = st.sidebar.number_input("Кількість панелей (шт)", value=22)
    system_capacity_kw = (panel_power_w * panel_count) / 1000.0
    
    loss_percent = st.sidebar.slider("Загальні втрати системи (%)", 5, 30, 14)
    system_loss = loss_percent / 100.0
    
    st.sidebar.info(f"⚡ Розрахункова потужність СЕС: **{system_capacity_kw:.2f} кВт**")

else:
    st.sidebar.subheader("Панелі")
    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
    module_name = st.sidebar.selectbox("Оберіть модуль", sandia_modules.columns)
    panel_count = st.sidebar.number_input("Кількість панелей (шт)", value=20)
    
    selected_module = sandia_modules[module_name]
    p_mp = selected_module.get('Pmp', 200)
    system_capacity_kw = (p_mp * panel_count) / 1000.0
    
    st.sidebar.subheader("Інвертор")
    cec_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
    inverter_name = st.sidebar.selectbox("Оберіть інвертор", cec_inverters.columns)
    
    loss_percent = st.sidebar.slider("Додаткові втрати (кабелі, бруд) (%)", 1, 20, 5)
    system_loss = loss_percent / 100.0
    
    st.sidebar.info(f"⚡ Потужність масиву панелей: **{system_capacity_kw:.2f} кВт**")

# Кнопка запуску розрахунку
if st.button("🚀 Розрахувати генерацію", type="primary"):
    with st.spinner("Завантаження погодних даних та розрахунок..."):
        try:
            # Отримання TMY даних з PVGIS
            tmy_data, _, _, _ = pvlib.iotools.get_pvgis_tmy(latitude, longitude, map_variables=True)
            
            # Розрахунок позиції сонця та інсоляції
            solpos = pvlib.solarposition.get_solarposition(tmy_data.index, latitude, longitude)
            total_irrad = pvlib.irradiance.get_total_irradiance(
                surface_tilt=tilt,
                surface_azimuth=azimuth,
                solar_zenith=solpos['zenith'],
                solar_azimuth=solpos['azimuth'],
                dni=tmy_data['dni'],
                ghi=tmy_data['ghi'],
                dhi=tmy_data['dhi']
            )
            
            poa_global = total_irrad['poa_global']
            
            # Спрощений розрахунок виробітку
            hourly_gen = (poa_global / 1000.0) * system_capacity_kw * (1 - system_loss)
            
            # Агрегація
            df_hourly = pd.DataFrame({'Generation_kWh': hourly_gen})
            
            # Помісячно
            monthly_gen = df_hourly.resample('ME').sum()
            monthly_gen['Місяць'] = monthly_gen.index.strftime('%B')
            
            # Потижнево
            weekly_gen = df_hourly.resample('W').sum()
            weekly_gen['Тиждень'] = [f"Тиждень {i+1}" for i in range(len(weekly_gen))]

            # Вкладки з результатами
            tab1, tab2, tab3 = st.tabs(["📊 Помісячний розрахунок", "📅 Потижневий розрахунок", "💾 Завантажити дані"])
            
            with tab1:
                col1, col2 = st.columns([2, 1])
                with col1:
                    fig_m = px.bar(
                        monthly_gen, x='Місяць', y='Generation_kWh', 
                        title="Помісячна генерація (кВт·год)",
                        text_auto='.0f', color='Generation_kWh',
                        color_continuous_scale="Oranges"
                    )
                    st.plotly_chart(fig_m, use_container_width=True)
                with col2:
                    st.subheader("Підсумки")
                    total_annual = df_hourly['Generation_kWh'].sum()
                    st.metric("Річний виробіток", f"{total_annual:,.0f} кВт·год")
                    st.dataframe(monthly_gen[['Generation_kWh']].rename(columns={'Generation_kWh': 'кВт·год'}), height=350)

            with tab2:
                fig_w = px.line(
                    weekly_gen, x='Тиждень', y='Generation_kWh', 
                    title="Потижнева динаміка генерації (кВт·год)",
                    markers=True
                )
                st.plotly_chart(fig_w, use_container_width=True)
                st.dataframe(weekly_gen[['Generation_kWh']].rename(columns={'Generation_kWh': 'кВт·год'}))

            with tab3:
                st.write("Завантажити результати у форматі CSV:")
                st.download_button(
                    label="📥 Завантажити потижневий звіт",
                    data=weekly_gen.to_csv().encode('utf-8'),
                    file_name='solar_weekly_generation.csv',
                    mime='text/csv'
                )

        except Exception as e:
            st.error(f"Помилка під час розрахунку: {e}")
