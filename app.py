import io
import os
import zipfile
import re
import arabic_reshaper
from bidi.algorithm import get_display
import matplotlib.pyplot as plt
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
import time
from datetime import datetime, timedelta

# --- GitHub Integration ---
from github import Github

# --- Selenium Imports for University Portal ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from PIL import Image

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
        
        /* Style the horizontal divider lines (---) to be bold and red */
            [data-testid="stSidebar"] hr {{
                margin-top: 0.8rem !important;
                margin-bottom: 0.8rem !important;
                border-top: 3px solid #ff4b4b !important; /* Makes it 3px thick and Red */
                border-bottom: none !important;
                border-left: none !important;
                border-right: none !important;
                opacity: 1 !important; /* Removes Streamlit's default faded/transparent look */
            }}

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
            padding: 1rem 0.8rem 0.5rem 0.8rem !important;
            background-color: #1a1a1a !important;
            border-radius: 8px !important;
            border: 1px solid #2a2a2a !important;
            margin-bottom: 12px !important;
        }

        /* 1. THE BREAKTHROUGH: Apply the default gray border to the OUTERMOST widget shell */
            [data-testid="stSidebar"] div[data-testid="stTextInput"] {{
                border: 1px solid #777777 !important; 
                border-radius: 6px !important;
                background-color: #1a1a1a !important;
                overflow: hidden !important; 
                margin-bottom: 12px !important; /* <--- THIS PUSHES THE BOXES APART */
            }}
        
        /* =========================================
           NUCLEAR CSS: DESTROY TOOLTIPS & TICK BARS
           ========================================= */
        
        [data-testid="stTickBar"], 
        [data-testid="stTickBarMin"], 
        [data-testid="stTickBarMax"] {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }

        div[data-baseweb="tooltip"], 
        div[role="tooltip"],
        div[data-testid="stThumbValue"] {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }

        div[data-baseweb="slider"] div[role="slider"] {
            background-color: #ff4d4d !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        
        div[data-baseweb="slider"][aria-disabled="true"] div[role="slider"] {
            background-color: #555555 !important;
        }

        [data-testid="stHorizontalBlock"] {
            align-items: center !important;
        }
        
    </style>
""",
    unsafe_allow_html=True,
)

st.title("Dynamic Timetable Generator")

html_content = ""
if st.session_state.get("live_html_data"):
    html_content = st.session_state.live_html_data
elif os.path.exists("data.html"):
    with open("data.html", "r", encoding="utf-8") as f:
        html_content = f.read()

time_match = re.search(r"<!-- SYNC_TIME: (.*?) -->", html_content)
updated_str = time_match.group(1) if time_match else "No data file found"

# ==========================================
# 2. TWO-STEP INTERACTIVE SELENIUM LOGIC
# ==========================================

def init_browser_and_get_captcha():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get("https://sso.iu.edu.sa")
        time.sleep(2) 
        
        try:
            uni_login_btn = driver.find_element(By.XPATH, "//*[contains(text(), 'الجامعي') or contains(text(), 'Employee')]")
            if uni_login_btn.is_displayed():
                driver.execute_script("arguments[0].click();", uni_login_btn)
                time.sleep(1)
        except:
            pass 

        try:
            captcha_img_element = driver.find_element(By.XPATH, "//img[contains(translate(@src, 'CAPTCHA', 'captcha'), 'captcha')]")
        except:
            captcha_img_element = driver.find_element(By.XPATH, "(//form//img)[last()]")
            
        img_bytes = captcha_img_element.screenshot_as_png
        
        st.session_state.live_driver = driver
        st.session_state.captcha_img_bytes = img_bytes
        st.session_state.waiting_for_captcha = True
        
    except Exception as e:
        driver.quit()
        raise Exception(f"Failed to initialize login page. {str(e)}")


def submit_captcha_and_scrape(username, password, captcha_val):
    driver = st.session_state.live_driver
    try:
        text_inputs = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//input[@type='text' and not(@type='hidden')]"))
        )
        user_field = text_inputs[0]
        captcha_input = text_inputs[-1] 
        pass_field = driver.find_element(By.XPATH, "//input[@type='password']")
        
        user_field.clear()
        user_field.send_keys(username)
        pass_field.clear()
        pass_field.send_keys(password)
        captcha_input.clear()
        captcha_input.send_keys(captcha_val)
        
        time.sleep(0.5) 
        captcha_input.send_keys(Keys.RETURN)
        
        try:
            WebDriverWait(driver, 15).until(EC.url_contains("Dashboard"))
        except:
            driver.save_screenshot("error_screenshot.png")
            raise Exception("Login rejected! Please check your Student ID, Password, or CAPTCHA.")
            
        # Generate our KSA timestamp once to inject into both files
        ksa_time = datetime.utcnow() + timedelta(hours=3)
        time_str = ksa_time.strftime("%d/%m/%Y at %I:%M %p")
            
        # --- POST-LOGIN NAVIGATION ---
        driver.get("https://cas.iu.edu.sa/cas/eregister")
        
        WebDriverWait(driver, 35).until(
            EC.url_contains("homeIndex.faces")
        )
        
        # 1. Open Menu
        electronic_reg_menu = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'التسجيل الإلكتروني') or contains(., 'Electronic')]"))
        )
        driver.execute_script("arguments[0].click();", electronic_reg_menu)
        time.sleep(1.5) 

        # 2. Click "المقررات المسجلة" (Enrolled Courses)
        enrolled_menu = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'المقررات المسجلة')]"))
        )
        driver.execute_script("arguments[0].click();", enrolled_menu)
        time.sleep(4) 
        
        # 3. Extract the Shuba IDs & save the raw enrolled HTML
        soup_enrolled = BeautifulSoup(driver.page_source, "html.parser")
        
        enrolled_tbody = None
        for tbody in soup_enrolled.find_all("tbody"):
            first_tr = tbody.find("tr")
            if first_tr and first_tr.has_attr("class") and len(first_tr["class"]) > 0 and first_tr["class"][0] in ["ROW1", "ROW2"]:
                enrolled_tbody = tbody
                break
                
        enrolled_ids = []
        if enrolled_tbody:
            for tr in enrolled_tbody.find_all("tr", class_=lambda c: c in ["ROW1", "ROW2"]):
                cols = tr.find_all("td")
                if len(cols) >= 4:
                    shuba = cols[3].text.strip()
                    if shuba.isdigit():
                        enrolled_ids.append(shuba)
                        
        enrolled_str = ", ".join(enrolled_ids)
        raw_enrolled_html = f"<!-- SYNC_TIME: {time_str} -->\n" + str(enrolled_tbody) if enrolled_tbody else f"<!-- SYNC_TIME: {time_str} -->\n<tbody></tbody>"

        # 4. Open Menu Again
        electronic_reg_menu = driver.find_element(By.XPATH, "//a[contains(., 'التسجيل الإلكتروني') or contains(., 'Electronic')]")
        driver.execute_script("arguments[0].click();", electronic_reg_menu)
        time.sleep(1.5)

        # 5. Click "المقررات المطروحة وفق الخطة" (Course Plan)
        course_plan_menu = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'المقررات المطروحة وفق الخطة') or contains(., 'Course')]"))
        )
        driver.execute_script("arguments[0].click();", course_plan_menu)
        
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        target_tbody = None
        
        for tbody in soup.find_all("tbody"):
            first_tr = tbody.find("tr")
            if first_tr and first_tr.has_attr("class"):
                target_tbody = tbody
                break
                
        if target_tbody is None:
            driver.save_screenshot("error_screenshot.png")
            raise Exception("Could not find the main timetable <tbody>.")
            
        final_html = f"<!-- SYNC_TIME: {time_str} -->\n" + str(target_tbody)
        
        # We now return 3 items: Main Data, Enrolled Data, and Enrolled String
        return final_html, raw_enrolled_html, enrolled_str
        
    finally:
        driver.quit()
        st.session_state.live_driver = None
        st.session_state.waiting_for_captcha = False


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


# GitHub Push Helper
def push_to_github(repo, file_path, content, commit_message):
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, commit_message, content, contents.sha)
    except Exception:
        repo.create_file(file_path, commit_message, content)


# ==========================================
# 4. INITIALIZE DATA & INTERACTIVE CAPTCHA
# ==========================================

if "live_html_data" not in st.session_state:
    st.session_state.live_html_data = None
if "waiting_for_captcha" not in st.session_state:
    st.session_state.waiting_for_captcha = False
if "live_driver" not in st.session_state:
    st.session_state.live_driver = None
if "captcha_img_bytes" not in st.session_state:
    st.session_state.captcha_img_bytes = None

import base64

# Convert CAPTCHA bytes for CSS background injection
captcha_b64 = base64.b64encode(st.session_state.captcha_img_bytes).decode("utf-8") if st.session_state.captcha_img_bytes else ""

st.markdown(
            f"""
            <style>
            /* Targets our specific CAPTCHA text input */
            [data-testid="stSidebar"] input[aria-label^="CAPTCHA"] {{
                background-image: url("data:image/png;base64,{captcha_b64}") !important;
                background-position: right 6px center !important;
                background-size: 106px 34px !important;
                background-repeat: no-repeat !important;
                padding-right: 120px !important; 
            }}
            
            /* 1. THE BREAKTHROUGH: Apply the default gray border to the OUTERMOST widget shell */
            [data-testid="stSidebar"] div[data-testid="stTextInput"] {{
                border: 1px solid #777777 !important; 
                border-radius: 6px !important;
                background-color: #1a1a1a !important;
                overflow: hidden !important; 
                margin-bottom: 12px !important; /* <--- Pushes the input boxes apart */
            }}
            
            /* 2. FOCUS STATE: The outermost shell turns red when you click inside */
            [data-testid="stSidebar"] div[data-testid="stTextInput"]:focus-within {{
                border: 1px solid #ff4b4b !important;
                box-shadow: 0 0 0 1px #ff4b4b !important;
            }}

            /* 3. STRIP THE INSIDE: Completely disarm Streamlit's hidden inner borders & radii */
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="input"],
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="base-input"],
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="base-input"]:focus-within,
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="input"]:focus,
            [data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="base-input"]:focus {{
                border: none !important;
                background-color: transparent !important;
                box-shadow: none !important;
                outline: none !important;
                border-radius: 0px !important; 
            }}

            /* 4. TEXT INPUT STYLING */
            [data-testid="stSidebar"] [data-testid="stTextInput"] input {{
                color: #ffffff !important;
                background-color: transparent !important; 
                height: 44px !important; 
                padding: 10px 12px !important;
                font-size: 15px !important;
                border: none !important; 
                outline: none !important;
                box-shadow: none !important;
            }}

            /* Placeholder text color */
            [data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder {{
                color: #888888 !important; 
            }}

            /* Keep the password eye icon background transparent */
            [data-testid="stSidebar"] [data-testid="stTextInput"] div[role="button"] {{
                background-color: transparent !important;
            }}
            
            /* 5. FORM LAYOUT & CLEANUP */
            /* Form container border removal & Top Gap Equalizer */
            [data-testid="stForm"] {{
                border: none !important;
                padding: 0 !important;
                margin-top: 14px !important; 
                background-color: transparent !important;
            }}

            /* Completely delete the "Press Enter to submit form" text */
            [data-testid="stSidebar"] [data-testid="InputInstructions"], 
            [data-testid="stSidebar"] div[data-testid="stFormSubmitInstructions"] {{
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
                height: 0 !important;
                width: 0 !important;
            }}
            
            /* 6. PRIMARY BUTTON STYLING */
            [data-testid="stSidebar"] button[kind="primary"] {{
                background-color: #ff4b4b !important; 
                border: none !important;
                color: #ffffff !important;
                font-weight: bold !important;
                font-size: 16px !important;
                border-radius: 6px !important;
                padding: 12px !important;
                margin-top: 4px !important;
            }}
            [data-testid="stSidebar"] button[kind="primary"]:hover {{
                background-color: #ff3333 !important;
            }}

          /* =========================================
               7. REFINED UX & SPACING (Clean & Modern)
               ========================================= */
               
            /* Keep the top flush so the header aligns nicely */
            [data-testid="stSidebarUserContent"] {{
                padding-top: 0rem !important; 
            }}

            /* Relax the gaps slightly so elements aren't suffocating */
            [data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {{
                gap: 0.8rem !important; 
            }}

            /* Clean typography spacing */
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {{
                margin-top: 0 !important;
                margin-bottom: 0 !important;
                line-height: 1.3 !important;
            }}

            /* Elegant, modern section dividers */
            [data-testid="stSidebar"] hr {{
                margin-top: 1.5rem !important;
                margin-bottom: 1.5rem !important;
                border-top: 1px solid rgba(255, 255, 255, 0.15) !important; /* <--- Subtle, semi-transparent line */
                border-bottom: none !important;
                border-left: none !important;
                border-right: none !important;
                opacity: 1 !important; 
            }}
            
            </style>
            """,
            unsafe_allow_html=True
        )

st.sidebar.markdown("<h3 style='text-align: left; color: white;'>🌐 Fetch Data From University Portal</h3>", unsafe_allow_html=True)

# --- PHASE 1: Fetch Captcha Session ---
if not st.session_state.waiting_for_captcha:
    if st.sidebar.button("Login And Scrap Data from Portal", use_container_width=True):
        if os.path.exists("error_screenshot.png"):
            os.remove("error_screenshot.png")
            
        with st.sidebar.spinner("Connecting to University Portal"):
            try:
                init_browser_and_get_captcha()
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error: {e}")

# --- PHASE 2: The UI Form ---
else:
    import base64
    import io
    from PIL import Image, ImageOps
    
    # 1. Dynamically invert, remove background, and inject the CAPTCHA
    if st.session_state.get("captcha_img_bytes"):
        try:
            # Load the original image bytes into a Pillow Image
            image_stream = io.BytesIO(st.session_state.captcha_img_bytes)
            
            # Convert to standard RGB (required for the invert function)
            img = Image.open(image_stream).convert("RGB") 
            
            # Invert the image colors (White background becomes black)
            inverted_img = ImageOps.invert(img)
            
            # Convert to RGBA so we can manipulate the Alpha (transparency) channel
            rgba_img = inverted_img.convert("RGBA")
            data = rgba_img.getdata()
            
            # Loop through pixels to make the black background transparent
            new_data = []
            for item in data:
                # Find very dark pixels (the new background) and make them transparent
                if item[0] < 50 and item[1] < 50 and item[2] < 50:
                    new_data.append((255, 255, 255, 0)) # 0 Alpha = Transparent
                else:
                    new_data.append(item) # Keep the text and noise lines visible
                    
            rgba_img.putdata(new_data)
            
            # Save the transparent image back to a bytes buffer
            buffered = io.BytesIO()
            rgba_img.save(buffered, format="PNG") # PNG is required to keep transparency
            
            # Encode the new image to Base64
            captcha_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
        except Exception as e:
            # Fallback to the original image just in case processing fails
            captcha_b64 = base64.b64encode(st.session_state.captcha_img_bytes).decode("utf-8")
            
        st.markdown(
            f"""
            <style>
            /* Targets our specific CAPTCHA text input below */
            [data-testid="stSidebar"] input[aria-label^="CAPTCHA"] {{
                /* Just the transparent CAPTCHA image now! */
                background-image: url("data:image/png;base64,{captcha_b64}") !important;
                background-position: right 6px center !important;
                background-size: 106px 34px !important;
                background-repeat: no-repeat !important;
                
                /* Push the typing cursor left so user text doesn't overlap the image */
                padding-right: 120px !important; 
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

    # 2. Build the Form using standard, natively perfectly aligned inputs
    with st.sidebar.form(key="login_form", clear_on_submit=False):
        
        portal_user = st.text_input("ID", placeholder="Enter Student ID", label_visibility="collapsed")
        
        portal_pass = st.text_input("Pass", type="password", placeholder="Enter Password", label_visibility="collapsed")
        
        # This SINGLE native box now dynamically paints the transparent image inside its right edge!
        user_captcha = st.text_input("CAPTCHA", placeholder="Enter Captcha Code", max_chars=5, label_visibility="collapsed")
        
        submit_form = st.form_submit_button("Continue", type="primary", use_container_width=True)
        
    # 3. Handle Submit
    if submit_form:
        if not portal_user or not portal_pass:
            st.sidebar.error("Please enter your Student ID and Password.")
        elif not user_captcha or len(user_captcha) != 5:
            st.sidebar.error("Please enter exactly 5 digits for the CAPTCHA.")
        else:
            with st.sidebar.spinner("Fetching Data From Portal"):
                try:
                    st.session_state.portal_user = portal_user
                    st.session_state.portal_pass = portal_pass
                    
                    raw_live_html, raw_enrolled_html, auto_enrolled = submit_captcha_and_scrape(
                        st.session_state.portal_user, 
                        st.session_state.portal_pass, 
                        user_captcha
                    )
                    st.session_state.live_html_data = raw_live_html
                    st.session_state.auto_enrolled = auto_enrolled
                    
                    with open("data.html", "w", encoding="utf-8") as f:
                        f.write(raw_live_html)
                    with open("enrolled.html", "w", encoding="utf-8") as f:
                        f.write(raw_enrolled_html)
                        
                    if "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
                        try:
                            g = Github(st.secrets["GITHUB_TOKEN"])
                            repo = g.get_repo(st.secrets["GITHUB_REPO"])
                            push_to_github(repo, "data.html", raw_live_html, "Bot synced timetable <tbody>")
                            push_to_github(repo, "enrolled.html", raw_enrolled_html, "Bot synced enrolled classes <tbody>")
                            st.sidebar.success("✅ Synced and pushed both files to GitHub!")
                        except Exception as github_e:
                            st.sidebar.warning(f"Saved locally, but GitHub push failed: {github_e}")
                    else:
                        st.sidebar.success("✅ Saved locally (GitHub secrets not configured).")
                    
                    if os.path.exists("error_screenshot.png"):
                        os.remove("error_screenshot.png")
                        
                    st.rerun() 
                        
                except Exception as e:
                    st.sidebar.error(f"Sync failed: {e}")
                    if st.session_state.live_driver:
                        st.session_state.live_driver.quit()
                        st.session_state.live_driver = None
                    st.session_state.waiting_for_captcha = False
                    st.stop()

    # 2. Build the Form using standard, natively perfectly aligned inputs
        
    # 3. Handle Submit
    if submit_form:
        if not portal_user or not portal_pass:
            st.sidebar.error("Please enter your Student ID and Password.")
        elif not user_captcha or len(user_captcha) != 5:
            st.sidebar.error("Please enter exactly 5 digits for the CAPTCHA.")
        else:
            with st.spinner("Scraping table and extracting <tbody>... (takes ~25s)"):
                try:
                    st.session_state.portal_user = portal_user
                    st.session_state.portal_pass = portal_pass
                    
                    raw_live_html, raw_enrolled_html, auto_enrolled = submit_captcha_and_scrape(
                        st.session_state.portal_user, 
                        st.session_state.portal_pass, 
                        user_captcha
                    )
                    st.session_state.live_html_data = raw_live_html
                    st.session_state.auto_enrolled = auto_enrolled
                    
                    with open("data.html", "w", encoding="utf-8") as f:
                        f.write(raw_live_html)
                    with open("enrolled.html", "w", encoding="utf-8") as f:
                        f.write(raw_enrolled_html)
                        
                    if "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
                        try:
                            g = Github(st.secrets["GITHUB_TOKEN"])
                            repo = g.get_repo(st.secrets["GITHUB_REPO"])
                            push_to_github(repo, "data.html", raw_live_html, "Bot synced timetable <tbody>")
                            push_to_github(repo, "enrolled.html", raw_enrolled_html, "Bot synced enrolled classes <tbody>")
                            st.sidebar.success("✅ Synced and pushed both files to GitHub!")
                        except Exception as github_e:
                            st.sidebar.warning(f"Saved locally, but GitHub push failed: {github_e}")
                    else:
                        st.sidebar.success("✅ Saved locally (GitHub secrets not configured).")
                    
                    if os.path.exists("error_screenshot.png"):
                        os.remove("error_screenshot.png")
                        
                    st.rerun() 
                        
                except Exception as e:
                    st.sidebar.error(f"Sync failed: {e}")
                    if st.session_state.live_driver:
                        st.session_state.live_driver.quit()
                        st.session_state.live_driver = None
                    st.session_state.waiting_for_captcha = False
                    st.stop()
                    
# Last Update On:
st.sidebar.markdown(
    f"<p style='color: #a0a0a0; font-size: 16px; margin-top: -12px; margin-bottom: 20px;'>"
    f"<b>Last Update:</b> {updated_str}"
    f"</p>",
    unsafe_allow_html=True,
)

# Read main data
raw_df = pd.DataFrame() 
if st.session_state.live_html_data:
    raw_df = parse_html_to_dataframe(st.session_state.live_html_data)
elif os.path.exists("data.html"):
    with open("data.html", "r", encoding="utf-8") as f:
        html_content = f.read()
        if html_content.strip():
            raw_df = parse_html_to_dataframe(html_content)

# Safety kill switch
if raw_df is None or raw_df.empty:
    if st.session_state.waiting_for_captcha:
        pass # Let the user fill out the form
    else:
        st.error("⚠️ No schedule data found. Please login to fetch fresh data.")
        if os.path.exists("error_screenshot.png"):
            st.image("error_screenshot.png", caption="Bot's view during the last failed attempt:")
    st.stop()


# ==========================================
# EXPORT SCRAPED SHUBA/ID DATA (EXCEL)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export Raw Data")

try:
    current_time_str = datetime.now().strftime("%d%m%Y-%H%M")
    excel_filename = f"Scraped_Shuba_Data_{current_time_str}.xlsx"
    
    raw_excel_buffer = io.BytesIO()
    with pd.ExcelWriter(raw_excel_buffer, engine='openpyxl') as writer:
        raw_df.to_excel(writer, index=False, sheet_name="Scraped_Data")
    
    st.sidebar.download_button(
        label="Download All Scraped Data (Excel)",
        data=raw_excel_buffer.getvalue(),
        file_name=excel_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
except ModuleNotFoundError:
    st.sidebar.error("⚠️ Add 'openpyxl' to requirements.txt to enable Excel downloads.")


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

if parsed_df.empty:
    st.error("⚠️ The scraped data contains no valid schedule blocks. The university portal might be empty.")
    st.stop()


# ==========================================
# 5. PURE NATIVE STREAMLIT FILTERS (Tight UI)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("Filter By Day & Time")

days_config = {
    1: ("Sunday (Day 1)", True),
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


# ==========================================
# 5B. ENROLLMENT & AVAILABILITY OVERRIDES
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("Section Availability")

# 1. Silently read Enrolled HTML in the background (No UI Text Box)
enrolled_ids_str = st.session_state.get("auto_enrolled", "")
enrolled_ids = [s.strip() for s in enrolled_ids_str.split(",") if s.strip()]

if not enrolled_ids and os.path.exists("enrolled.html"):
    with open("enrolled.html", "r", encoding="utf-8") as f:
        soup_enc = BeautifulSoup(f.read(), "html.parser")
        for tr in soup_enc.find_all("tr", class_=lambda c: c in ["ROW1", "ROW2"]):
            cols = tr.find_all("td")
            if len(cols) >= 4:
                sh = cols[3].text.strip()
                if sh.isdigit():
                    enrolled_ids.append(sh)

# 2. Apply logic with the new Checkbox
if "STATUS" in raw_df.columns:
    auto_remove = st.sidebar.checkbox("Remove Closed Sections", value=True)
    protect_enrolled = st.sidebar.checkbox("Mark enrolled sections as opened", value=True)
    
    if auto_remove:
        closed_mask = valid_blocks_df["STATUS"].astype(str).str.contains("مغلقة", na=False)
        
        if protect_enrolled and enrolled_ids:
            # Skip closed sections, BUT treat enrolled sections as opened!
            is_enrolled_mask = valid_blocks_df["ID"].astype(str).isin(enrolled_ids)
            valid_blocks_df = valid_blocks_df[~closed_mask | is_enrolled_mask]
        else:
            valid_blocks_df = valid_blocks_df[~closed_mask]


# ==========================================
# 6. GLOBAL HALL & SHUBA RULES (REQUIRE / BAN)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("Global Hall & Shuba Rules")

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
    
    col_zip, col_excel = st.columns(2)
    
    # --- 1. ZIP JPG DOWNLOAD ---
    with col_zip:
        if st.button("Render All as JPGs (ZIP)", key="download_zip_btn", use_container_width=True):
            with st.spinner("Drawing high-res images..."):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for i, sched in enumerate(schedules):
                        img_bytes = draw_schedule_image(sched)
                        zip_file.writestr(f"Schedule_Option_{i+1}.jpg", img_bytes)
      
                st.download_button(
                    label="📥 Click Here to Download ZIP",
                    data=zip_buffer.getvalue(),
                    file_name="All_Schedules.zip",
                    mime="application/zip",
                    use_container_width=True
                )
            
    # --- 2. ALL SCHEDULES EXCEL DOWNLOAD ---
    with col_excel:
        try:
            import openpyxl
            all_excel_buffer = io.BytesIO()
            with pd.ExcelWriter(all_excel_buffer, engine='openpyxl') as writer:
                for i, sched in enumerate(schedules):
                    df_sched = pd.DataFrame([{
                        "CODE": s["code"],
                        "NAME": s["name"],
                        "ID (ش)": s["id"],
                        "HALL": s["hall"],
                        "VENUE": s["venue"],
                        "TEACHER": s["teacher"],
                        "STATUS": s["status"],
                    } for s in sched])
                    # Put each schedule on its own sheet in the Excel file
                    df_sched.to_excel(writer, index=False, sheet_name=f"Option_{i+1}")
            
            st.download_button(
                label="📥 Download All Schedules (1 Excel File)",
                data=all_excel_buffer.getvalue(),
                file_name="All_Generated_Schedules.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ModuleNotFoundError:
            st.error("⚠️ Please add 'openpyxl' to your requirements.txt to enable Excel downloads.")

    st.markdown("</div>", unsafe_allow_html=True)
