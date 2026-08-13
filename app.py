import io
import os
import zipfile
import arabic_reshaper
from bidi.algorithm import get_display
import matplotlib.pyplot as plt
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
import time

# --- Selenium Imports for University Portal ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 1. STREAMLIT CONFIGURATION & THEME STYLING
# ==========================================
st.set_page_config(page_title="Dynamic Timetable Solver", layout="wide")

st.markdown(
    """
    <style>
        .stCaption {display: none;}
        
        /* 4-Color Theme: Black, Dark Gray, Light Gray, White */
        .stApp {
            background-color: #000000;
            color: #ffffff;
        }
        
        [data-testid="stSidebar"] {
            background-color: #121212;
            color: #ffffff;
        }

        h1 {
            font-size: clamp(1.2rem, 2.5vw, 2.2rem) !important;
            white-space: nowrap !important;
            color: #ffffff !important;
        }

        .nav-row {
            display: flex;
            flex-direction: row;
            align-items: center;
            width: 100%;
            gap: 8px;
            margin-bottom: 15px;
        }
        .nav-row > div:nth-child(1),
        .nav-row > div:nth-child(3) {
            flex: 0 0 50px !important;
        }
        .nav-row > div:nth-child(2) {
            flex: 1 1 auto !important;
        }

        .center-download {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 100%;
            margin-top: 20px;
            text-align: center;
        }
        
        /* =========================================
           UI TIGHTENING CSS (Squish Elements in Card) 
           ========================================= */
        
        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1rem 0.8rem 0.8rem 0.8rem !important;
            background-color: #1a1a1a !important;
            border-radius: 8px !important;
            border: 1px solid #2a2a2a !important;
            margin-bottom: 12px !important;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"] {
            gap: 0.2rem !important;
        }

        [data-testid="stSidebar"] [data-testid="stTextInput"] input {
            font-size: 0.85rem !important;
            background-color: #121212 !important;
            border-color: #333333 !important;
            margin-top: 5px !important;
        }

        /* =========================================
           CLEAN SLIDER CSS (ONLY ONE SET OF NUMBERS)
           ========================================= */
        
        [data-testid="stTickBar"] {
            display: none !important;
        }

        div[data-baseweb="slider"] div[data-testid="stThumbValue"] {
            background-color: transparent !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            padding: 0 !important;
            box-shadow: none !important;
            border: none !important;
            transform: translateY(24px) !important;
        }

        div[data-baseweb="slider"] div[data-testid="stThumbValue"] svg {
            display: none !important;
        }

        div[data-baseweb="slider"] div[role="slider"] {
            width: 16px !important;
            height: 16px !important;
            background-color: #ff4d4d !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        
        div[data-baseweb="slider"][aria-disabled="true"] div[role="slider"] {
            background-color: #555555 !important;
        }
        div[data-baseweb="slider"][aria-disabled="true"] div[data-testid="stThumbValue"] {
            color: #777777 !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("Dynamic Timetable Generator")

# ==========================================
# 2. LIVE UNIVERSITY PORTAL SCRAPING LOGIC
# ==========================================
def fetch_live_portal_data(username, password):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # 1. Force Selenium to use the exact Chrome binary installed by Streamlit Cloud
    options.binary_location = "/usr/bin/chromium"
    
    # 2. Force Selenium to use the exact matched driver installed by Streamlit Cloud
    service = Service("/usr/bin/chromedriver")
    
    # Initialize hidden Chrome browser using the system drivers
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # 1. Access the initial login page
        driver.get("https://sso.iu.edu.sa")
        
        # 2. Wait for login fields to appear and input credentials
        user_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        pass_field = driver.find_element(By.NAME, "password")
        
        user_field.send_keys(username)
        pass_field.send_keys(password)
        
        # Click the login submission button
        pass_field.submit() 
        
        # 3. Wait to enter dashboard, then trigger the academic jump
        WebDriverWait(driver, 15).until(EC.url_contains("Dashboard"))
        driver.get("https://cas.iu.edu.sa/cas/eregister")
        
        # Wait until it successfully lands on the specific .faces UI index
        WebDriverWait(driver, 15).until(EC.url_contains("homeIndex.faces"))
        
        # 4. Navigate through the JavaServer Faces (.faces) Menu clicks
        electronic_reg_menu = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "
                                التسجيل الإلكتروني"))
        )
        electronic_reg_menu.click()
        
        course_plan_menu = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "المقررات المطروحة وفق الخطة"))
        )
        course_plan_menu.click()
        
        # 5. Wait for the data table to physically render in the DOM
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@id, ':instructor')]"))
        )
        
        # 6. Extract the generated page source
        return driver.page_source

    finally:
        driver.quit()
        
# ==========================================
# 3. EMBEDDED HTML PARSER & DATA EXTRACTOR
# ==========================================
def parse_html_to_dataframe(html_content):
  soup = BeautifulSoup(html_content, "html.parser")
  extracted_rows = []

  rows = soup.find_all("tr")
  for row in rows:
    cols = row.find_all("td")
    if not cols or len(cols) < 7:
      continue

    code = cols[0].text.strip()
    name = cols[1].text.strip()
    course_id = cols[2].text.strip()
    status = cols[5].text.strip()

    instructor_input = cols[6].find(
        "input", id=lambda x: x and x.endswith(":instructor")
    )
    section_input = cols[6].find(
        "input", id=lambda x: x and x.endswith(":section")
    )

    raw_instructor = (
        instructor_input["value"].strip() if instructor_input else ""
    )
    raw_section = section_input["value"].strip() if section_input else ""

    teacher = "TBD" if "لم يحدد" in raw_instructor else raw_instructor

    venue_list = []
    hall = ""

    if "@t" in raw_section and "@r" in raw_section:
      sessions = raw_section.split("@n")
      for session in sessions:
        session = session.strip()
        if not session:
          continue

        parts = session.split("@t")
        days = parts[0].strip().split()
        time_and_room = parts[1].split("@r")
        time_str = time_and_room[0].strip()
        room = time_and_room[1].strip()

        start_time = time_str.split("-")[0].strip()
        try:
          raw_hour = int(start_time.split(":")[0].strip())
          if "م" in start_time and raw_hour != 12:
            raw_hour += 12
          elif "ص" in start_time and raw_hour == 12:
            raw_hour = 0
          hour = f"{raw_hour:02d}"
        except ValueError:
          hour = time_str.split(":")[0].strip()

        for day in days:
          venue_list.append(f"{day}- {hour}")

        if not hall:
          hall = f"SHR {room}"

    venue_list.sort()
    venue_final = ", ".join(venue_list)
    if venue_final:
      venue_final = f"{venue_final}"

    extracted_rows.append({
        "CODE": code,
        "NAME": name,
        "ID": int(course_id) if course_id.isdigit() else course_id,
        "HALL": hall,
        "VENUE": venue_final,
        "TEACHER": teacher,
        "STATUS": status,
    })

  return pd.DataFrame(extracted_rows)

# ==========================================
# 4. INITIALIZE DATA (LIVE FETCH OR FALLBACK)
# ==========================================
st.sidebar.header("🌐 Live Portal Sync")
portal_user = st.sidebar.text_input("Portal Username", placeholder="Student ID")
portal_pass = st.sidebar.text_input("Portal Password", type="password", placeholder="Password")

if "live_html_data" not in st.session_state:
    st.session_state.live_html_data = None

if st.sidebar.button("Fetch Live Timetable", use_container_width=True):
    if not portal_user or not portal_pass:
        st.sidebar.error("Please enter credentials.")
    else:
        with st.spinner("Connecting to IU portal... (This takes a few moments)"):
            try:
                raw_live_html = fetch_live_portal_data(portal_user, portal_pass)
                st.session_state.live_html_data = raw_live_html
                st.sidebar.success("Successfully synced with portal!")
            except Exception as e:
                st.sidebar.error(f"Sync failed. Ensure credentials are correct. Error: {e}")

st.sidebar.markdown("---")

# Determine which data to use: Live data (if fetched) OR local fallback file
if st.session_state.live_html_data:
    raw_df = parse_html_to_dataframe(st.session_state.live_html_data)
elif os.path.exists("data.html"):
    with open("data.html", "r", encoding="utf-8") as f:
        raw_df = parse_html_to_dataframe(f.read())
else:
    st.error("No live data fetched and 'data.html' fallback file not found. Please sync with the portal.")
    st.stop()


@st.cache_data
def parse_schedule_blocks(df_input):
  parsed_rows = []
  for index, row in df_input.iterrows():
    venue_str = str(row["VENUE"]).strip()
    if venue_str == "nan" or not venue_str:
      continue

    blocks = [b.strip() for b in venue_str.split(",")]
    for block in blocks:
      if "-" in block:
        parts = block.split("-")
        try:
          day = int(parts[0].strip())
          start_time = int(parts[1].strip())
          new_row = row.copy()
          new_row["day"] = day
          new_row["start_time"] = start_time
          new_row["end_time"] = start_time + 1
          parsed_rows.append(new_row)
        except ValueError:
          continue
  return pd.DataFrame(parsed_rows)

parsed_df = parse_schedule_blocks(raw_df)

# ==========================================
# 5. PURE NATIVE STREAMLIT FILTERS (Tight UI)
# ==========================================
st.sidebar.header("Day & Time Matrix Filters")

days_config = {
    1: ("Sunday (Day 1)", False),
    2: ("Monday (Day 2)", True),
    3: ("Tuesday (Day 3)", True),
    4: ("Wednesday (Day 4)", True),
    5: ("Thursday (Day 5)", True),
}

day_filters = {}
day_exceptions = {}

for day_num, (label, default_val) in days_config.items():
  with st.sidebar.container(border=True):
    is_on = st.checkbox(label, value=default_val, key=f"chk_{day_num}")

    if is_on:
      time_range = st.slider(
          "Hours", 8, 18, (8, 18), 
          format="%02d",
          key=f"slide_{day_num}", 
          label_visibility="collapsed"
      )
      
      ex_list = []
      exception_str = st.text_input(
          "Exceptions", 
          value="",
          placeholder="Enter Excepted Hours", 
          key=f"txt_{day_num}", 
          label_visibility="collapsed"
      )
      if exception_str.strip():
        try:
          ex_list = [int(x.strip()) for x in exception_str.split(",") if x.strip().isdigit()]
        except ValueError:
          pass

      day_filters[day_num] = {"range": time_range}
      day_exceptions[day_num] = ex_list

    else:
      st.slider(
          "Hours", 8, 18, (8, 18), 
          format="%02d",
          disabled=True, 
          key=f"slide_dis_{day_num}", 
          label_visibility="collapsed"
      )
      
      st.text_input(
          "Exceptions", 
          value="",
          placeholder="Enter Excepted Hours", 
          key=f"txt_dis_{day_num}", 
          label_visibility="collapsed",
          disabled=True
      )
      
      day_filters[day_num] = None
      day_exceptions[day_num] = []

def is_valid_time(row):
  day, start = row["day"], row["start_time"]
  config = day_filters.get(day)
  if config is not None:
    r_start, r_end = config["range"]
    if r_start <= start <= r_end:
      if start not in day_exceptions.get(day, []):
        return True
  return False

parsed_df["is_valid"] = parsed_df.apply(is_valid_time, axis=1)
invalid_ids = parsed_df[parsed_df["is_valid"] == False]["ID"].unique()
valid_blocks_df = parsed_df[~parsed_df["ID"].isin(invalid_ids)]

# --- Section Availability Filter ---
st.sidebar.markdown("---")
st.sidebar.header("Section Availability")
if "STATUS" in raw_df.columns:
  auto_remove = st.sidebar.checkbox("Auto-Remove Closed Sections", value=True)
  if auto_remove:
    closed_mask = valid_blocks_df["STATUS"].astype(str).str.contains(
        "مغلقة", na=False
    )
    valid_blocks_df = valid_blocks_df[~closed_mask]

# ==========================================
# 6. GLOBAL HALL & SHUBA RULES (REQUIRE / BAN)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("Global Hall & Shuba Rules")
st.sidebar.caption("Global filters to require or ban specific Halls and Shubas.")

all_halls = sorted(
    [str(h) for h in raw_df["HALL"].dropna().astype(str).unique() if h.strip()]
)
all_shubas = sorted(
    [str(s) for s in raw_df["ID"].dropna().astype(str).unique() if s.strip()]
)

banned_halls = st.sidebar.multiselect(
    "Ban Halls", options=all_halls, key="global_ban_halls"
)
remaining_halls = [h for h in all_halls if h not in banned_halls]
required_halls = st.sidebar.multiselect(
    "Require Halls", options=remaining_halls, key="global_req_halls"
)

banned_shubas = st.sidebar.multiselect(
    "Ban Shubas (IDs)", options=all_shubas, key="global_ban_shubas"
)
remaining_shubas = [s for s in all_shubas if s not in banned_shubas]
required_shubas = st.sidebar.multiselect(
    "Require Shubas (IDs)", options=remaining_shubas, key="global_req_shubas"
)

# Apply Hall filters
if banned_halls:
  valid_blocks_df = valid_blocks_df[
      ~valid_blocks_df["HALL"].astype(str).isin(banned_halls)
  ]
if required_halls:
  valid_blocks_df = valid_blocks_df[
      valid_blocks_df["HALL"].astype(str).isin(required_halls)
  ]

# Apply Shuba filters
if banned_shubas:
  valid_blocks_df = valid_blocks_df[
      ~valid_blocks_df["ID"].astype(str).isin(banned_shubas)
  ]
if required_shubas:
  valid_blocks_df = valid_blocks_df[
      valid_blocks_df["ID"].astype(str).isin(required_shubas)
  ]

# ==========================================
# 7. SUBJECT-SPECIFIC TEACHER RULES
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("Subject-Specific Teacher Rules")
st.sidebar.caption("Expand each subject to ban or require specific teachers.")

all_subjects = sorted([str(c) for c in raw_df["CODE"].astype(str).unique()])

subject_rules = {}
for subj in all_subjects:
  subj_name_row = raw_df[raw_df["CODE"].astype(str) == subj]
  subj_name = subj_name_row["NAME"].iloc[0] if not subj_name_row.empty else ""

  with st.sidebar.expander(f"📚 {subj_name} ({subj})"):
    teachers_for_subj = sorted(
        raw_df[raw_df["CODE"].astype(str) == subj]["TEACHER"].astype(str).unique()
    )

    banned_t = st.multiselect(
        "Ban Teachers", options=teachers_for_subj, key=f"ban_{subj}"
    )
    remaining_t = [t for t in teachers_for_subj if t not in banned_t]
    required_t = st.multiselect(
        "Require Teacher", options=remaining_t, key=f"req_{subj}"
    )

    subject_rules[subj] = {"ban": banned_t, "require": required_t}

for subj, rules in subject_rules.items():
  if rules["ban"]:
    valid_blocks_df = valid_blocks_df[
        ~(
            (valid_blocks_df["CODE"].astype(str) == subj)
            & (valid_blocks_df["TEACHER"].isin(rules["ban"]))
        )
    ]
  if rules["require"]:
    valid_blocks_df = valid_blocks_df[
        ~(
            (valid_blocks_df["CODE"].astype(str) == subj)
            & (~valid_blocks_df["TEACHER"].isin(rules["require"]))
        )
    ]

# ==========================================
# 8. DATA GROUPING & SOLVER
# ==========================================
sections_by_subject = {}
for code, group in valid_blocks_df.groupby("CODE"):
  sections_by_subject[str(code)] = []
  for sec_id, sec_group in group.groupby("ID"):
    blocks = [
        {"day": r["day"], "start_time": r["start_time"]}
        for _, r in sec_group.iterrows()
    ]
    matching_row = raw_df[raw_df["ID"] == sec_id].iloc[0]

    sections_by_subject[str(code)].append({
        "code": str(code),
        "name": matching_row["NAME"],
        "id": sec_id,
        "hall": matching_row["HALL"],
        "venue": matching_row["VENUE"],
        "teacher": matching_row["TEACHER"],
        "status": matching_row.get("STATUS", "N/A"),
        "blocks": blocks,
    })

target_subjects = list(sections_by_subject.keys())
total_required_subjects = len(all_subjects)

if len(target_subjects) < total_required_subjects:
  st.warning(
      f"Only {len(target_subjects)} out of {total_required_subjects} valid"
      " subjects remaining after filters. Check your filters or rules."
  )

@st.cache_data
def generate_schedules(subjects_dict, targets):
  valid_schedules = []

  def backtrack(idx, current_schedule, occupied_slots):
    if len(valid_schedules) >= 50:
      return
    if idx == len(targets):
      valid_schedules.append(list(current_schedule))
      return
    for section in subjects_dict[targets[idx]]:
      overlap = False
      for b in section["blocks"]:
        if (b["day"], b["start_time"]) in occupied_slots:
          overlap = True
          break
      if not overlap:
        current_schedule.append(section)
        for b in section["blocks"]:
          occupied_slots.add((b["day"], b["start_time"]))
        backtrack(idx + 1, current_schedule, occupied_slots)
        current_schedule.pop()
        for b in section["blocks"]:
          occupied_slots.remove((b["day"], b["start_time"]))

  backtrack(0, [], set())
  return valid_schedules


schedules = (
    generate_schedules(sections_by_subject, target_subjects)
    if target_subjects
    else []
)

def calculate_schedule_score(schedule):
  day_slots = {}
  for sec in schedule:
    for b in sec["blocks"]:
      d, t = b["day"], b["start_time"]
      if d not in day_slots:
        day_slots[d] = []
      day_slots[d].append(t)

  total_gaps = 0
  for d, times in day_slots.items():
    times = sorted(list(set(times)))
    if len(times) > 1:
      span = (max(times) + 1) - min(times)
      gaps = span - len(times)
      total_gaps += gaps
  return total_gaps

schedules = sorted(schedules, key=calculate_schedule_score)

# ==========================================
# 9. IMAGE GENERATOR & UI RENDERING
# ==========================================

def fix_arabic(text):
  if not text.strip():
    return ""
  return get_display(arabic_reshaper.reshape(str(text)))

def draw_schedule_image(schedule):
  fig, ax = plt.subplots(figsize=(10, 6))
  ax.axis("tight")
  ax.axis("off")

  cols = ["الخميس", "الأربعاء", "الثلاثاء", "الاثنين", "الأحد", "الوقت"]
  cols_reshaped = [fix_arabic(c) for c in cols]

  cell_text = [["" for _ in range(6)] for _ in range(11)]
  col_map = {1: 4, 2: 3, 3: 2, 4: 1, 5: 0}

  for row_idx in range(11):
    hour = 8 + row_idx
    cell_text[row_idx][5] = f"{hour}:00"

  for section in schedule:
    cell_label = fix_arabic(f"{section['code']} (ش {section['id']})")
    for b in section["blocks"]:
      if 8 <= b["start_time"] <= 18:
        row_idx = b["start_time"] - 8
        col_idx = col_map.get(b["day"])
        if col_idx is not None and row_idx < 11:
          cell_text[row_idx][col_idx] = cell_label

  table = ax.table(
      cellText=cell_text,
      colLabels=cols_reshaped,
      loc="center",
      cellLoc="center",
  )
  table.scale(1, 2)

  for (row, col), cell in table.get_celld().items():
    cell.set_text_props(fontname="Segoe UI", size=12)
    if row == 0:
      cell.set_facecolor("#212121")
      cell.get_text().set_color("white")
      cell.get_text().set_weight("bold")
    elif col == 5:
      cell.set_facecolor("#212121")
      cell.get_text().set_color("white")
      cell.get_text().set_weight("bold")
    else:
      if cell_text[row - 1][col].strip() != "":
        cell.set_facecolor("#ffffff")
        cell.get_text().set_color("#000000")
      else:
        cell.set_facecolor("#424242")

  buf = io.BytesIO()
  plt.savefig(buf, format="jpg", dpi=300, bbox_inches="tight")
  buf.seek(0)
  plt.close(fig)
  return buf.getvalue()


if not schedules:
  st.warning("No valid non-overlapping schedules found with these filters.")
else:
  st.info(
      f"Found {len(schedules)} valid schedules (Ranked by least gaps)."
  )

  if "sched_idx" not in st.session_state:
    st.session_state.sched_idx = 0
  if "active_view" not in st.session_state:
    st.session_state.active_view = "Visual View"

  if st.session_state.sched_idx >= len(schedules):
    st.session_state.sched_idx = 0

  st.markdown('<div class="nav-row">', unsafe_allow_html=True)
  c_prev, c_sel, c_next = st.columns([1, 8, 1])

  with c_prev:
    if st.button("◀", key="prev_btn", use_container_width=True):
      if st.session_state.sched_idx > 0:
        st.session_state.sched_idx -= 1
      else:
        st.session_state.sched_idx = len(schedules) - 1
      st.rerun()

  with c_sel:
    selected_idx = st.selectbox(
        "Browse Schedule Options:",
        range(len(schedules)),
        index=st.session_state.sched_idx,
        format_func=lambda x: (
            f"Option #{x + 1} (Best Fit)" if x == 0 else f"Option #{x + 1}"
        ),
        label_visibility="collapsed",
    )
    if selected_idx != st.session_state.sched_idx:
      st.session_state.sched_idx = selected_idx
      st.rerun()

  with c_next:
    if st.button("▶", key="next_btn", use_container_width=True):
      if st.session_state.sched_idx < len(schedules) - 1:
        st.session_state.sched_idx += 1
      else:
        st.session_state.sched_idx = 0
      st.rerun()
  st.markdown("</div>", unsafe_allow_html=True)

  active_sched = schedules[st.session_state.sched_idx]

  is_visual = st.session_state.active_view == "Visual View"
  v_bg = "#000000" if is_visual else "#212121"
  v_border = "#ffffff" if is_visual else "#424242"

  is_excel = st.session_state.active_view == "Excel View"
  e_bg = "#000000" if is_excel else "#212121"
  e_border = "#ffffff" if is_excel else "#424242"

  col_btn1, col_btn2 = st.columns(2)
  with col_btn1:
    if st.button(
        "Visual View", use_container_width=True, key="btn_visual_toggle"
    ):
      st.session_state.active_view = "Visual View"
      st.rerun()
  with col_btn2:
    if st.button(
        "Excel View", use_container_width=True, key="btn_excel_toggle"
    ):
      st.session_state.active_view = "Excel View"
      st.rerun()

  st.markdown(
      f"""
        <style>
            div[data-testid="column"] button[key="btn_visual_toggle"] {{
                background-color: {v_bg} !important;
                color: #ffffff !important;
                border: 2px solid {v_border} !important;
                font-weight: bold;
            }}
            div[data-testid="column"] button[key="btn_excel_toggle"] {{
                background-color: {e_bg} !important;
                color: #ffffff !important;
                border: 2px solid {e_border} !important;
                font-weight: bold;
            }}
        </style>
    """,
      unsafe_allow_html=True,
  )

  if st.session_state.active_view == "Visual View":
    html_grid = "<table dir='rtl' style='width:100%; text-align:center; border-collapse: collapse; font-family: sans-serif; background-color: #121212; color: #ffffff;'>"
    html_grid += "<tr style='background-color: #212121; color: #ffffff;'>"
    html_grid += "<th style='border: 1px solid #333333; padding: 8px;'>الوقت</th><th style='border: 1px solid #333333; padding: 8px;'>الأحد</th><th style='border: 1px solid #333333; padding: 8px;'>الاثنين</th><th style='border: 1px solid #333333; padding: 8px;'>الثلاثاء</th><th style='border: 1px solid #333333; padding: 8px;'>الأربعاء</th><th style='border: 1px solid #333333; padding: 8px;'>الخميس</th></tr>"

    col_map_html = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

    for row_idx in range(11):
      hour = 8 + row_idx
      bg_color = "#121212" if row_idx % 2 == 0 else "#1a1a1a"
      html_grid += f"<tr style='background-color: {bg_color}; border: 1px solid #333333;'>"
      html_grid += f"<td style='background-color: #212121; color: #ffffff; border: 1px solid #333333; padding: 8px;'><b>{hour}:00</b></td>"

      row_cells = [""] * 5
      for section in active_sched:
        for b in section["blocks"]:
          if b["start_time"] == hour:
            c_idx = col_map_html.get(b["day"])
            if c_idx:
              row_cells[c_idx - 1] = (
                  f"<b>{section['code']}</b><br><small>(ش"
                  f" {section['id']})</small>"
              )

      for c in row_cells:
        cell_bg = "#ffffff" if c else "#212121"
        cell_fg = "#000000" if c else "#888888"
        html_grid += f"<td style='border: 1px solid #333333; padding: 10px; background-color: {cell_bg}; color: {cell_fg};'>{c}</td>"
      html_grid += "</tr>"
    html_grid += "</table>"

    st.markdown(html_grid, unsafe_allow_html=True)

  else:
    df_excel = pd.DataFrame([{
        "CODE": s["code"],
        "NAME": s["name"],
        "ID (ش)": s["id"],
        "HALL": s["hall"],
        "VENUE": s["venue"],
        "TEACHER": s["teacher"],
        "STATUS": s["status"],
    } for s in active_sched])

    st.dataframe(df_excel, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    try:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_excel.to_excel(writer, index=False, sheet_name="Schedule")
        
        st.download_button(
            label="📥 Download Current Schedule (Excel)",
            data=excel_buffer.getvalue(),
            file_name=f"Schedule_Option_{st.session_state.sched_idx + 1}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except ModuleNotFoundError:
        st.error("Please add 'openpyxl' to your requirements.txt to enable Excel downloads.")
        csv_data = df_excel.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Current Schedule (CSV Backup)",
            data=csv_data,
            file_name=f"Schedule_Option_{st.session_state.sched_idx + 1}.csv",
            mime="text/csv",
            use_container_width=True
        )

  st.markdown("---")
  st.markdown('<div class="center-download">', unsafe_allow_html=True)
  if st.button(
      "Render & Download All Schedules as JPGs (ZIP)", key="download_zip_btn"
  ):
    with st.spinner("Drawing high-res images..."):
      zip_buffer = io.BytesIO()
      with zipfile.ZipFile(
          zip_buffer, "a", zipfile.ZIP_DEFLATED, False
      ) as zip_file:
        for i, sched in enumerate(schedules):
          img_bytes = draw_schedule_image(sched)
          zip_file.writestr(f"Schedule_Option_{i+1}.jpg", img_bytes)

      st.download_button(
          label="Click Here to Download ZIP",
          data=zip_buffer.getvalue(),
          file_name="All_Schedules.zip",
          mime="application/zip",
      )
  st.markdown("</div>", unsafe_allow_html=True)
