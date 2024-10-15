from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("openai_api_key"))

async def generate_response(prompt):
    try:
        completion = await client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are HeyRehan, an AI assistant. Whenever a user interacts with you, you should introduce yourself as 'HeyRehan' and briefly explain that you help with translating text, generating images, and other tasks."},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error generating response: {str(e)}"
