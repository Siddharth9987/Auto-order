from flask import Flask, render_template, request
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import requests
import cv2
import numpy as np
import base64
import time
import os
import io
from PIL import Image
import pytesseract
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'

class CaptchaSolver:
    @staticmethod
    def download_image(driver, image_element):
        """Download CAPTCHA image from element"""
        try:
            img_base64 = driver.execute_script("""
                var canvas = document.createElement('canvas');
                var context = canvas.getContext('2d');
                var img = arguments[0];
                canvas.height = img.naturalHeight;
                canvas.width = img.naturalWidth;
                context.drawImage(img, 0, 0);
                return canvas.toDataURL();
                """, image_element)
            
            # Convert base64 to image
            img_data = base64.b64decode(img_base64.split(',')[1])
            img = Image.open(io.BytesIO(img_data))
            return img
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None

    @staticmethod
    def solve_image_captcha(driver):
        """Solve Amazon's image CAPTCHA"""
        try:
            # Wait for CAPTCHA image
            wait = WebDriverWait(driver, 10)
            captcha_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//img[contains(@src, 'captcha')]")
            ))

            # Download and process CAPTCHA image
            img = CaptchaSolver.download_image(driver, captcha_element)
            if img is None:
                return False

            # Preprocess image
            img = img.convert('L')  # Convert to grayscale
            img = img.point(lambda x: 0 if x < 128 else 255)  # Threshold
            
            # OCR to extract text
            captcha_text = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            captcha_text = ''.join(c for c in captcha_text if c.isalnum())

            if len(captcha_text) != 6:  # Amazon CAPTCHAs are usually 6 characters
                return False

            # Enter CAPTCHA
            captcha_input = wait.until(EC.presence_of_element_located(
                (By.ID, "captchacharacters")
            ))
            captcha_input.send_keys(captcha_text)
            
            # Submit CAPTCHA
            driver.find_element(By.XPATH, "//button[contains(.,'Continue shopping')]").click()
            time.sleep(2)

            # Check if CAPTCHA was solved successfully
            return "captcha" not in driver.current_url.lower()

        except Exception as e:
            print(f"Error solving image CAPTCHA: {e}")
            return False

    @staticmethod
    def solve_slider_captcha(driver):
        """Solve slider CAPTCHA with human-like movement"""
        try:
            wait = WebDriverWait(driver, 10)
            slider = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class, 'slider')]")
            ))

            # Get slider size and location
            slider_size = slider.size
            slider_location = slider.location

            # Create human-like movement
            actions = ActionChains(driver)
            actions.move_to_element(slider)
            actions.click_and_hold()

            # Generate natural movement path
            steps = np.linspace(0, slider_size['width'], num=20)
            for step in steps:
                actions.move_by_offset(step/10, np.random.randint(-2, 3))
                time.sleep(np.random.uniform(0.01, 0.05))

            actions.release()
            actions.perform()

            # Verify if slider CAPTCHA was solved
            time.sleep(2)
            return "slider" not in driver.current_url.lower()

        except Exception as e:
            print(f"Error solving slider CAPTCHA: {e}")
            return False

def automate_amazon(email, password, products):
    # Initialize Chrome with anti-detection measures
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=options)
    
    # Modify navigator.webdriver flag
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 15)

    try:
        # Login to Amazon
        driver.get('https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3F_encoding%3DUTF8%26ref_%3Dnav_ya_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0')
        
        # Handle email input and potential CAPTCHA
        wait.until(EC.presence_of_element_located((By.ID, 'ap_email'))).send_keys(email)
        driver.find_element(By.ID, 'continue').click()
        time.sleep(2)

        # Check for and solve any CAPTCHA
        if "captcha" in driver.current_url.lower():
            if not CaptchaSolver.solve_image_captcha(driver):
                if not CaptchaSolver.solve_slider_captcha(driver):
                    raise Exception("Failed to solve CAPTCHA")

        # Handle password input
        wait.until(EC.presence_of_element_located((By.ID, 'ap_password'))).send_keys(password)
        driver.find_element(By.ID, 'signInSubmit').click()
        time.sleep(2)

        # Process each product
        for _, row in products.iterrows():
            try:
                driver.get(row['product_link'])
                time.sleep(2)

                # Handle any product page CAPTCHA
                if "captcha" in driver.current_url.lower():
                    if not CaptchaSolver.solve_image_captcha(driver):
                        if not CaptchaSolver.solve_slider_captcha(driver):
                            continue

                # Set quantity and proceed with order
                try:
                    quantity_dropdown = wait.until(EC.presence_of_element_located((By.ID, 'quantity')))
                    quantity_dropdown.click()
                    driver.find_element(By.XPATH, f"//option[@value='{row['quantity']}']").click()
                except:
                    print("Quantity selection not available")

                # Click Buy Now and handle checkout
                wait.until(EC.element_to_be_clickable((By.ID, 'buy-now-button'))).click()
                time.sleep(2)

                # Handle checkout process with potential CAPTCHAs
                if "captcha" in driver.current_url.lower():
                    if not CaptchaSolver.solve_image_captcha(driver):
                        if not CaptchaSolver.solve_slider_captcha(driver):
                            continue

                # Complete order placement
                try:
                    wait.until(EC.element_to_be_clickable((By.NAME, 'placeYourOrder1'))).click()
                    time.sleep(3)
                except:
                    print("Error placing order")

            except Exception as e:
                print(f"Error processing product: {e}")
                continue

    except Exception as e:
        print(f"Automation error: {e}")
    finally:
        driver.quit()

# Your existing Flask routes remain the same
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    try:
        data = pd.read_excel(file_path)
        data.columns = data.columns.str.strip()

        required_columns = ['email', 'password', 'product_link', 'quantity']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            return f"Error: Missing required columns: {', '.join(missing_columns)}", 400

        email = data['email'][0]
        password = data['password'][0]
        products = data[['product_link', 'quantity']]

        automate_amazon(email, password, products)
        return "Order Placement Completed Successfully!"
    except Exception as e:
        return f"Error: {e}", 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)