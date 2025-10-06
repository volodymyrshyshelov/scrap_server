from flask import Flask, request, jsonify
import asyncio
import time
import requests
from playwright.async_api import async_playwright

app = Flask(__name__)

CAPTCHA_API_KEY = "45709a1a49dda43044e985d9d2e34d6d"
CAPTCHA_SITE_KEY = "6LciY5wkAAAAAJLIl-z-boIBPtOfSnj1h3bNvIPq"


def solve_recaptcha(page_url):
    create_task = requests.post("https://api.2captcha.com/createTask", json={
        "clientKey": CAPTCHA_API_KEY,
        "task": {
            "type": "RecaptchaV3TaskProxyless",
            "websiteURL": page_url,
            "websiteKey": CAPTCHA_SITE_KEY,
            "isEnterprise": True,
            "pageAction": "phone",
            "minScore": 0.3
        }
    })
    
    task_data = create_task.json()
    if task_data.get("errorId") != 0:
        raise Exception(f"2captcha error: {task_data}")
    
    task_id = task_data["taskId"]
    
    for _ in range(20):
        time.sleep(3)
        result = requests.post("https://api.2captcha.com/getTaskResult", json={
            "clientKey": CAPTCHA_API_KEY,
            "taskId": task_id
        })
        
        result_data = result.json()
        if result_data.get("status") == "ready":
            return result_data["solution"]["gRecaptchaResponse"]
    
    raise Exception("Captcha timeout")


async def get_phone(listing_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        token = solve_recaptcha(listing_url)
        
        await page.goto(listing_url, wait_until="networkidle")
        await page.wait_for_selector('button[aria-label="show-phone-button"]', timeout=10000)
        
        await page.evaluate(f"""
            window.captchaToken = '{token}';
            const originalFetch = window.fetch;
            window.fetch = function(...args) {{
                const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
                if (url.includes('/phone') && args[1]?.body) {{
                    try {{
                        const body = JSON.parse(args[1].body);
                        body.token = window.captchaToken;
                        args[1].body = JSON.stringify(body);
                    }} catch(e) {{}}
                }}
                return originalFetch.apply(this, args);
            }};
        """)
        
        phone_data = None
        
        async def handle_response(response):
            nonlocal phone_data
            if "/phone" in response.url and response.status == 201:
                try:
                    phone_data = await response.json()
                except:
                    pass
        
        page.on("response", handle_response)
        
        await page.click('button[aria-label="show-phone-button"]')
        await asyncio.sleep(3)
        
        if not phone_data:
            try:
                phone_text = await page.locator('button[aria-label="show-phone-button"] .MuiTypography-h6').text_content()
                phone_data = {"phone": phone_text}
            except:
                pass
        
        await browser.close()
        return phone_data


@app.route('/get-phone', methods=['POST'])
def get_phone_endpoint():
    data = request.json
    listing_url = data.get('url')
    
    if not listing_url:
        return jsonify({"error": "Missing url parameter"}), 400
    
    try:
        result = asyncio.run(get_phone(listing_url))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)