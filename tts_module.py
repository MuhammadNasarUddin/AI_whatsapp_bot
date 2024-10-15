from openai import AsyncOpenAI
from dotenv import load_dotenv
from quart import Quart, request, send_file
import os
import uuid

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("openai_api_key"))

async def text_to_speech(text):
    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )

        # Get the absolute path to the directory where the Python script is located
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Generate a unique filename
        unique_filename = f"output_{uuid.uuid4().hex}.mp3"
        output_file_path = os.path.join(script_dir, unique_filename)

        # Save the audio in MP3 format
        with open(output_file_path, "wb") as audio_file:
            audio_file.write(response.content)

        # Return the filename
        return unique_filename
    except Exception as e:
        raise Exception(f"Text-to-speech conversion failed: {str(e)}")
