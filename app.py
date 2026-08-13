# ==========================================
# 2. LIVE UNIVERSITY PORTAL SCRAPING LOGIC
# ==========================================
def fetch_live_portal_data(username, password):
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
        # 1. Access the initial login page
        driver.get("https://sso.iu.edu.sa")
        
        # 2. SMART LOGIN SELECTORS (Handles standard, .NET Identity, and Arabic forms)
        # Find the first valid text/email input (Username)
        user_field = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='text' or @type='email' or contains(@name, 'Username') or contains(@name, 'user')]"))
        )
        
        # Find the password input
        pass_field = driver.find_element(By.XPATH, "//input[@type='password']")
        
        # Clear fields and type credentials
        user_field.clear()
        user_field.send_keys(username)
        pass_field.clear()
        pass_field.send_keys(password)
        
        # Find and click the Submit/Login button instead of using the enter key
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit'] | //input[@type='submit'] | //button[contains(., 'دخول')] | //button[contains(., 'Login')]")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        # 3. Wait to enter dashboard
        WebDriverWait(driver, 25).until(EC.url_contains("Dashboard"))
        
        # Trigger the academic jump
        driver.get("https://cas.iu.edu.sa/cas/eregister")
        
        # Wait for the logininit bridge to finish processing
        WebDriverWait(driver, 35).until(
            EC.url_contains("homeIndex.faces")
        )
        
        # 4. Navigate through the Menus
        electronic_reg_menu = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'التسجيل الإلكتروني')]"))
        )
        driver.execute_script("arguments[0].click();", electronic_reg_menu)
        
        time.sleep(1.5) # Let the menu animation finish
        
        course_plan_menu = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'المقررات المطروحة وفق الخطة')]"))
        )
        driver.execute_script("arguments[0].click();", course_plan_menu)
        
        # 5. Wait for the data table to physically render in the DOM
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@id, ':instructor')]"))
        )
        
        return driver.page_source

    except Exception as e:
        # Take a screenshot to show exactly where the bot failed
        driver.save_screenshot("error_screenshot.png")
        raise Exception(f"Stuck at URL: {driver.current_url}")

    finally:
        driver.quit()
