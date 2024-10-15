import yt_dlp
from pydub import AudioSegment
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
import aiohttp
import asyncio
import logging
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

client = AsyncOpenAI(api_key=os.getenv('openai_api_key'))

MAX_CONTENT_SIZE = 25 * 1024 * 1024  # 25 MB

def read_cookies(file_path='cookies.txt'):
    if os.path.exists(file_path):
        return file_path
    else:
        logging.error(f"Cookies file not found: {file_path}")
        return None

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

async def translate_audio(file_path):
    try:
        file_size = os.path.getsize(file_path)
        if file_size > MAX_CONTENT_SIZE:
            logging.error(f"File size {file_size} exceeds the maximum allowed size of {MAX_CONTENT_SIZE}")
            return None
        
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as audio_file:
                logging.info(f"Translating audio file: {file_path}")
                translation = await client.audio.translations.create(
                    model="whisper-1", 
                    file=audio_file
                )
        logging.info(f"Translation completed successfully")
        return translation.text
    except Exception as e:
        logging.error(f"Error translating audio: {e}")
        return None

async def abstract_summary_extraction(text):
    try:
        logging.info("Generating summary from translated text")
        completion = await client.chat.completions.create(
            model="gpt-4-turbo",
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

async def process_youtube_video(video_url):
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





