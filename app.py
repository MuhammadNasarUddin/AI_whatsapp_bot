import mysql.connector
import logging
import uuid
import asyncio
import requests
import os
import time
import tempfile
from datetime import datetime, timedelta
from dotenv import load_dotenv
from quart import Quart, request, send_file, render_template
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from help_text import generate_help_text
from payment import generate_payment_url, handle_successful_payment
from gpt_module import generate_response
from dalle_module import generate_image
from tts_module import text_to_speech
from translate_module import translate_text
from tokens_usage import generate_tokens_usage_text
from topup_sample import topup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import yt_dlp
from pydub import AudioSegment
import speech_recognition as sr
from openai import AsyncOpenAI
import aiohttp

load_dotenv()

app = Quart(__name__)
logging.basicConfig(level=logging.INFO)

# OpenAI client
ai = AsyncOpenAI(api_key=os.getenv("openai_api_key"))

# Twilio credentials
account_sid = os.getenv('twilio_account_sid')
auth_token = os.getenv('twilio_auth_token')
twilio_number = os.getenv('twilio_whatsapp_number')
client = Client(account_sid, auth_token)

# Audio files cache
audio_files = {}

# Maximum content size for translations
MAX_CONTENT_SIZE = 25 * 1024 * 1024  # 25 MB

# Database connection
def get_database_connection():
    return mysql.connector.connect(
        host='209.38.157.26',
        user='myadmin',
        password='Admin@1234',
        database='whatsapp_bot',
    )

# Function to save cookies
def save_cookies(driver, location):
    with open(location, 'w') as file:
        # Write the header for Netscape format
        file.write("# Netscape HTTP Cookie File\n")
        file.write("# This is a generated file! Do not edit.\n\n")

        # Iterate through all cookies
        for cookie in driver.get_cookies():
            # Format each cookie as expected in Netscape format
            # DOMAIN, flag, PATH, SECURE, EXPIRATION, NAME, VALUE
            domain = cookie['domain']
            flag = 'TRUE' if domain.startswith('.') else 'FALSE'
            path = cookie['path']
            secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
            expiration = str(int(cookie['expiry'])) if 'expiry' in cookie else '0'
            name = cookie['name']
            value = cookie['value']
            file.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")

# Function to log in to YouTube and save cookies
def login_youtube(email, password):
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run Chrome in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.get("https://accounts.google.com/ServiceLogin?service=youtube")

    # Wait until the email input field is present
    try:
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "identifierId"))
        )
        email_input.send_keys(email)
        email_input.send_keys(Keys.RETURN)
    except Exception as e:
        logging.error(f"Failed to find email input field: {e}")
        driver.quit()
        return False

    # Wait for the password input field to be visible and interactable
    try:
        password_input = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.XPATH, "//input[@type='password']"))
        )
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='password']"))
        )
        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)
    except Exception as e:
        logging.error(f"Failed to interact with password input field: {e}")
        driver.save_screenshot('error_screenshot.png')
        with open('page_source.html', 'w') as file:
            file.write(driver.page_source)
        driver.quit()
        return False

    # Wait for some time to ensure login completes
    time.sleep(5)

    # Navigate to YouTube to ensure YouTube cookies are set
    driver.get("https://www.youtube.com/")
    time.sleep(5)  # Wait for YouTube to load and set cookies

    # Save cookies to a file
    save_cookies(driver, "cookies.txt")
    driver.quit()
    return True

# Function to read cookies from file
def read_cookies(file_path='cookies.txt'):
    if os.path.exists(file_path):
        return file_path
    else:
        logging.error(f"Cookies file not found: {file_path}")
        return None

# Function to download audio from YouTube video
async def download_audio(video_url, retries=5):
    cookies_file = read_cookies()
    if not cookies_file:
        return None

    options = {
        'format': 'bestaudio/best',
        'outtmpl': 'audio.%(ext)s',
        'quiet': True,
        'cookiefile': cookies_file,  # Path to your cookies file
    }
    ydl = yt_dlp.YoutubeDL(options)
    attempt = 0
    while attempt < retries:
        try:
            logging.info(f"Attempting to download audio from {video_url}, attempt {attempt + 1}")
            ydl.download([video_url])
            for file in os.listdir():
                if file.startswith('audio'):
                    logging.info(f"Downloaded audio file: {file}")
                    return file
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"Download attempt {attempt + 1} failed: {e}")
            attempt += 1
            await asyncio.sleep(5)
    return None

# Function to convert audio file to MP3
async def convert_to_mp3(input_file):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_mp3:
            audio = AudioSegment.from_file(input_file)
            audio.export(temp_mp3.name, format="mp3")
            logging.info(f"Conversion to MP3 completed successfully: {temp_mp3.name}")
            return temp_mp3.name
    except Exception as e:
        logging.error(f"Error converting to MP3: {e}")
        return None

# Function to translate audio to text
async def translate_audio(file_path):
    try:
        file_size = os.path.getsize(file_path)
        if file_size > MAX_CONTENT_SIZE:
            logging.error(f"File size {file_size} exceeds the maximum allowed size of {MAX_CONTENT_SIZE}")
            return None
        
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as audio_file:
                logging.info(f"Translating audio file: {file_path}")
                translation = await ai.audio.translations.create(
                    model="whisper-1", 
                    file=audio_file
                )
        logging.info(f"Translation completed successfully")
        return translation.text
    except Exception as e:
        logging.error(f"Error translating audio: {e}")
        return None

# Function to generate summary from translated text
async def abstract_summary_extraction(text):
    try:
        logging.info("Generating summary from translated text")
        completion = await ai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "You are a highly skilled AI trained in language comprehension and summarization. I would like you to read the following text and summarize it into a concise abstract paragraph. Aim to retain the most important points, providing a coherent and readable summary that could help a person understand the main points of the discussion without needing to read the entire text. Please avoid unnecessary details or tangential points."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )
        logging.info("Summary generation completed successfully")
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating summary: {e}")
        return None

# Function to process YouTube video for summarization
async def process_youtube_video(video_url):
    if not login_youtube('example@gmail.com','example123'):
        return "Error logging into YouTube. Please check your credentials."

    try:
        downloaded_file = await download_audio(video_url)
        if not downloaded_file:
            logging.error("Error downloading the audio.")
            return "Error downloading the audio. Please check the video URL or try again later."
        
        mp3_file = await convert_to_mp3(downloaded_file)
        if not mp3_file:
            logging.error("Error converting to MP3.")
            return "Error converting to MP3. Please try again later."
        
        translation_text = await translate_audio(mp3_file)
        if not translation_text:
            logging.error("Error translating audio.")
            return "Error translating audio. The file size might be too large. Please try again later."
        
        summary = await abstract_summary_extraction(translation_text)
        if not summary:
            logging.error("Error generating summary.")
            return "Error generating summary. Please try again later."
        
        # Clean up temporary files
        try:
            os.remove(mp3_file)
            os.remove(downloaded_file)
            logging.info("Temporary files cleaned up successfully")
        except Exception as e:
            logging.error(f"Error cleaning up files: {e}")

        return summary
    
    except Exception as e:
        logging.error(f"Error processing video: {e}")
        return "An error occurred while processing the video. Please try again later."

@app.route('/webhook', methods=['POST'])
async def whatsapp_bot():
    incoming_msg = (await request.values).get('Body', '').strip()
    phone_number = (await request.values).get('From', '').strip()

    # Record the time when the request is received
    start_time = time.time()

    response = MessagingResponse()

    media_url = (await request.values).get('MediaUrl0', '')
    media_type = (await request.values).get('MediaContentType0', '')

    conn = get_database_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users WHERE phone_number=%s", (phone_number,))
        user = cursor.fetchone()

        if not user:
            # Generate a UUID for new user
            user_id = str(uuid.uuid4())
            # If the user is new, insert their information with default tokens
            cursor.execute("INSERT INTO users (user_id, phone_number, tokens) VALUES (%s, %s, 10)", (user_id, phone_number,))
            conn.commit()
            client.messages.create(
                body="Welcome to Hey Rehan! You have been granted 10 free tokens to get started. Type /help for more information on how to use it.",
                from_=twilio_number,
                to=phone_number
            )
        else:
            user_id = user[0]
            tokens_balance = user[2]  # Get the tokens balance

            

            if media_url:
                audio_file = download_audio_file(media_url, media_type)
                if audio_file:
                    audio_files[phone_number] = audio_file
                    client.messages.create(
                        body="What should I do with this audio, kindly?\n1. Get Text\n2. Chat with ChatGPT",
                        from_=twilio_number,
                        to=phone_number
                    )
                else:
                    client.messages.create(
                        body="There was an issue downloading the audio file.",
                        from_=twilio_number,
                        to=phone_number
                    )
                return str(response)

            # Check if incoming_msg is a command that requires immediate processing
            immediate_processing = False
            if incoming_msg.startswith(('/chat', '/imagine', '/voice', '/translation')):
                immediate_processing = True

            # If it's not an immediate command, check the time taken for processing
            if not immediate_processing:
                # Calculate the time taken for processing
                end_time = time.time()
                processing_time = end_time - start_time

                # If processing time exceeds 5 seconds, set immediate_processing to True
                if processing_time > 5:
                    immediate_processing = True

            # If immediate_processing is True, send the initial response message
            if immediate_processing:
                client.messages.create(
                    body="Bot is processing your request, please wait a moment...",
                    from_=twilio_number,
                    to=phone_number
                )

            # Handle the incoming message
            if incoming_msg.startswith('/help'):
                # Show help message without deducting tokens
                client.messages.create(
                    body=generate_help_text(),
                    from_=twilio_number,
                    to=phone_number
                )

            elif incoming_msg.startswith('/topup'):
                # Prompt user to select a package if their balance is insufficient
                client.messages.create(
                    body=topup(),
                    from_=twilio_number,
                    to=phone_number
                )


            elif incoming_msg.lower() == 'unlimited_10':
                # Generate payment URL for Annual 500 tokens package
                payment_url = generate_payment_url('unlimited_10', user_id)
                client.messages.create(
                    body=f"Click here to subscribe to the unlimited package for $10/month: {payment_url}",
                    from_=twilio_number,
                    to=phone_number
                )

            
            elif tokens_balance <= 0:
                # If user's tokens are over, notify them and prevent further processing
                client.messages.create(
                    body="Your free tokens are over. To continue using our services, please top up your tokens.",
                    from_=twilio_number,
                    to=phone_number
                )
            
            else:
                if phone_number in audio_files:
                    await handle_audio_action(phone_number, incoming_msg)
                else:
                    # Create an asynchronous task to handle long queries
                    asyncio.create_task(handle_long_query(incoming_msg, user_id, tokens_balance, phone_number))

    except Exception as e:
        client.messages.create(
            body=f"An error occurred: {str(e)}",
            from_=twilio_number,
            to=phone_number
        )

    finally:
        # Close cursor and connection
        cursor.close()
        conn.close()

    return str(response)

async def handle_long_query(incoming_msg, user_id, tokens_balance, phone_number):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # Extract the command and convert it to lowercase
        parts = incoming_msg.split(' ', 1)
        command = parts[0].lower()
        rest_of_message = parts[1] if len(parts) > 1 else ''

        if command == '/imagine':
            # Process image prompt
            if tokens_balance < 4:
                client.messages.create(
                    body="You don't have enough tokens to use the /imagine command. Please top up your tokens.",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                logging.info(f"user input: {incoming_msg}")
                img_prompt = rest_of_message.strip()
                logging.info(f"prompt: {img_prompt}")
                img_url = await generate_image(img_prompt)
                logging.info(f"image url: {img_url}")
                client.messages.create(
                    media_url=img_url,
                    from_=twilio_number,
                    to=phone_number
                )
                # Deduct 4 tokens for image message
                cursor.execute("UPDATE users SET tokens = tokens - 4 WHERE user_id=%s", (user_id,))
                conn.commit()

                

        elif command == '/translation':
            # Process translation prompt
            if tokens_balance < 2:
                client.messages.create(
                    body="You don't have enough tokens to use the /translation command. Please top up your tokens.",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                logging.info(f"user input: {incoming_msg}")
                text = rest_of_message.strip()
                logging.info(f"text: {text}")
                translated_text = translate_text(text)
                logging.info(f"translated text: {translated_text}")
                client.messages.create(
                    body=translated_text,
                    from_=twilio_number,
                    to=phone_number
                )
                # Deduct 2 tokens for translation message
                cursor.execute("UPDATE users SET tokens = tokens - 2 WHERE user_id=%s", (user_id,))
                conn.commit()

        elif command == '/tokens':
            # Show tokens balance
            client.messages.create(
                body=generate_tokens_usage_text(tokens_balance),
                from_=twilio_number,
                to=phone_number
            )

        elif command == '/voice':
            # Process voice prompt
            if tokens_balance < 3:
                client.messages.create(
                    body="You don't have enough tokens to use the /voice command. Please top up your tokens.",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                logging.info(f"user input: {incoming_msg}")
                text = rest_of_message.strip()
                logging.info(f"text: {text}")
                tts_response = await text_to_speech(text)
                logging.info(f"tts response: {tts_response}")
                client.messages.create(
                    media_url=f"https://bot.didx.net/audio/{tts_response}",
                    from_=twilio_number,
                    to=phone_number
                )
                # Deduct 3 tokens for voice message
                cursor.execute("UPDATE users SET tokens = tokens - 3 WHERE user_id=%s", (user_id,))
                conn.commit()

        else:
            # Process chat prompt by default
            if tokens_balance < 2:
                client.messages.create(
                    body="You don't have enough tokens to continue chatting. Please top up your tokens.",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                logging.info(f"user input: {incoming_msg}")
                response_text = await generate_response(incoming_msg)
                logging.info(f"response: {response_text}")
                client.messages.create(
                    body=response_text,
                    from_=twilio_number,
                    to=phone_number
                )
                # Deduct 2 tokens for chat message
                cursor.execute("UPDATE users SET tokens = tokens - 2 WHERE user_id=%s", (user_id,))
                conn.commit()

    except Exception as e:
        client.messages.create(
            body=f"An error occurred: {str(e)}",
            from_=twilio_number,
            to=phone_number
        )
    
    finally:
        cursor.close()
        conn.close()

def download_audio_file(media_url, content_type):
    try:
        response = requests.get(media_url, auth=(account_sid, auth_token))
        if response.status_code != 200:
            logging.error(f"Failed to download audio file: {response.status_code} {response.text}")
            return None

        extension = content_type.split('/')[1]
        file_name = f'audio.{extension}'
        
        with open(file_name, 'wb') as file:
            file.write(response.content)
        
        logging.debug(f"Audio file downloaded to: {file_name}")

        # Convert to WAV format if necessary
        if extension != 'wav':
            audio = AudioSegment.from_file(file_name)
            wav_file_name = 'audio.wav'
            audio.export(wav_file_name, format='wav')
            logging.debug(f"Audio file converted to WAV: {wav_file_name}")
            return wav_file_name
        return file_name
    except Exception as e:
        logging.error(f"Error downloading audio file: {e}")
        return None

async def handle_audio_action(phone_number, body):
    conn = get_database_connection()
    cursor = conn.cursor()
    audio_file = audio_files.pop(phone_number)
    response = MessagingResponse()

    try:
        # Fetch the user's current token balance
        cursor.execute("SELECT user_id, tokens FROM users WHERE phone_number=%s", (phone_number,))
        user = cursor.fetchone()
        if not user:
            client.messages.create(
                body="User not found. Please register first.",
                from_=twilio_number,
                to=phone_number
            )
            delete_audio_file(audio_file)
            return str(response)    

        user_id, tokens_balance = user

        if tokens_balance < 3:
            client.messages.create(
                body="You don't have enough tokens. Please top up your tokens.",
                from_=twilio_number,
                to=phone_number
            )
            delete_audio_file(audio_file)
            return str(response)

        if body in ['1', 'get text']:
            transcription = transcribe_audio(audio_file)
            if transcription:
                client.messages.create(
                    body=f"{transcription}",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                client.messages.create(
                    body="Sorry, I couldn't transcribe the audio.",
                    from_=twilio_number,
                    to=phone_number
                )
            delete_audio_file(audio_file)

        elif body in ['2', 'chat with chatgpt']:
            transcription = transcribe_audio(audio_file)
            if transcription:
                gpt_response = await generate_response(transcription)
                client.messages.create(
                    body=f"{gpt_response}",
                    from_=twilio_number,
                    to=phone_number
                )
            else:
                client.messages.create(
                    body="Sorry, I couldn't transcribe the audio.",
                    from_=twilio_number,
                    to=phone_number
                )
            delete_audio_file(audio_file)
        else:
            client.messages.create(
                body="Invalid choice. Please reply with '1' for Get Text or '2' for Chat with ChatGPT.",
                from_=twilio_number,
                to=phone_number
            )
            return str(response)

        # Deduct 3 tokens
        cursor.execute("UPDATE users SET tokens = tokens - 3 WHERE user_id=%s", (user_id,))
        conn.commit()

    except Exception as e:
        client.messages.create(
            body=f"An error occurred: {str(e)}",
            from_=twilio_number,
            to=phone_number
        )
    
    finally:
        cursor.close()
        conn.close()
    
    return str(response)

import whisper
import logging

def transcribe_audio(audio_file):
    try:
        model = whisper.load_model("small")  # Adjust model size based on your needs
        result = model.transcribe(audio_file)
        transcription = result['text']
        logging.debug(f"Transcription: {transcription}")
        return transcription
    except Exception as e:
        logging.error(f"Error during transcription: {e}")
        return None


def delete_audio_file(file_path):
    try:
        os.remove(file_path)
        logging.debug(f"Deleted audio file: {file_path}")
    except Exception as e:
        logging.error(f"Error deleting audio file: {e}")

@app.route('/generate_audio', methods=['POST'])
async def generate_audio():
    data = await request.get_json()
    text = data.get("text")
    if not text:
        return {"error": "Text is required"}, 400

    filename = await text_to_speech(text)
    audio_url = f"https://bot.didx.net/audio/{filename}"  # Ensure this URL is publicly accessible
    return {"audio_url": audio_url}

@app.route('/audio/<filename>')
async def audio(filename):
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)
    if not os.path.exists(file_path):
        return {"error": "File not found"}, 404

    return await send_file(file_path, as_attachment=True)

@app.route('/success')
async def payment_success():
    user_id = request.args.get('user_id')
    package = request.args.get('package')
    print("user_id:", user_id)
    print("package:", package)
    if user_id and package:
        new_tokens = handle_successful_payment(user_id, package)
        if new_tokens is not None:
            return await render_template('success.html', tokens=new_tokens)
        else:
            return "Payment successful, but there was an issue updating your tokens. Please contact support."
    else:
        return "Missing parameters. Please contact support."


@app.route('/cancel')
async def payment_cancel():
    return "Payment canceled. If you have any questions, please contact support."        



import time

def send_daily_message():
    conn = get_database_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT phone_number FROM users WHERE phone_number IS NOT NULL AND phone_number != ''")
        paid_users = cursor.fetchall()
        successful_sends = 0

        for user in paid_users:
            phone_number = user[0]
            try:
                client.messages.create(
                    body="How are you doing today? How can I help you?",
                    from_=twilio_number,
                    to=phone_number,
                     status_callback="https://bot.didx.net/twilio/status"

                    )
                successful_sends += 1
                time.sleep(1)  # Delay between messages to avoid rate limiting
            except Exception as e:
                logging.error(f"Failed to send message to {phone_number}: {e}")

        logging.info(f"Successfully sent messages to {successful_sends} users.")
        return successful_sends

    except Exception as e:
        logging.error(f"Error sending daily message: {e}")
    finally:
        cursor.close()
        conn.close()
     

def schedule_daily_messages(hour, minute):
    while True:
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if next_run < now:
            next_run += timedelta(days=1)

        sleep_duration = (next_run - now).total_seconds()
        logging.info(f"Scheduled to send daily messages at {next_run}. Sleeping for {sleep_duration} seconds.")
        
        time.sleep(sleep_duration)

        # Send daily messages
        send_daily_message()


from quart import request

@app.route('/twilio/status', methods=['POST'])
async def message_status():
    form_data = await request.form  # Asynchronous handling of form data
    message_sid = form_data.get('MessageSid')
    message_status = form_data.get('MessageStatus')
    phone_number = form_data.get('To')

    logging.info(f"Message SID: {message_sid}, Status: {message_status}, To: {phone_number}")

    # Process the status or save to database
    return "Status received", 200



if __name__ == '__main__':
    # Start the message scheduler in a separate thread
    from threading import Thread
    thread = Thread(target=schedule_daily_messages, args=(10, 0), daemon=True)
    thread.start()

    # # Run the Quart app
    app.run(port=80, host='0.0.0.0')

    # app.run(port=8001,)
