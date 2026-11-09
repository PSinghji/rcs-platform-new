import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
logger = logging.getLogger("rcs_notifications")

def send_campaign_alert(campaign_name, user_name, audience_count):
    """
    Sends an email alert to the admin when a new campaign is launched.
    """
    # --- CONFIGURATION ---
    SENDER_EMAIL = "rahulmskhandelwal@gmail.com"
    SENDER_PASSWORD = "hadhpltdagecufze"  # 16-character app password
    ADMIN_EMAIL = "pstanwarec@gmail.com" # The email that receives the alert
    
    # --- EMAIL CONTENT ---
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ADMIN_EMAIL
    msg['Subject'] = f"🚀 New Campaign Alert: {campaign_name}"

    now_ist = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="background-color: #0f172a; padding: 20px; text-align: center;">
            <h2 style="color: #3b82f6; margin: 0;">New Campaign Launched</h2>
        </div>
        <div style="padding: 20px; border: 1px solid #ddd; border-top: none;">
            <p><strong>Campaign Name:</strong> {campaign_name}</p>
            <p><strong>Created By:</strong> {user_name}</p>
            <p><strong>Total Audience:</strong> {audience_count}</p>
            <p><strong>Time (IST):</strong> {now_ist}</p>
            <hr style="border: 0; border-top: 1px solid #eee;">
            <p style="font-size: 12px; color: #666;">This is an automated notification from the RCS Hub Portal.</p>
        </div>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(body, 'html'))

    # --- SENDING LOGIC ---
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls() # Secure the connection
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            logger.info(f"✅ Admin notification sent for campaign: {campaign_name}")
    except Exception as e:
        logger.error(f"❌ Failed to send admin email: {str(e)}")