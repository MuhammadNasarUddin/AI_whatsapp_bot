from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import asyncio
import logging
load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("openai_api_key"))

async def generate_image(img):
    try:
        response = await client.images.generate(
            model="dall-e-3",
            prompt=img,
            n=1,
            size="1024x1024",
            quality="standard",
        )

        img_url = response.data[0].url
        logging.info(f"Generated image URL: {img_url}")  # Add this line to log the generated image URL
        return img_url
    except Exception as e:
        return str(e)

    