def generate_tokens_usage_text(tokens_balance):
    return f"""
Your remaining tokens balance is `{tokens_balance}`.

💰*Token Usage:*

🖼️ For Image prompt: 4 tokens

💬 For Chat prompt: 2 tokens

🎤 For Voice prompt: 3 tokens

🌐 For Translation prompt: 2 tokens

🔄 *To top up your tokens:*

Type `/topup` or use the commands `unlimited_10`.

ℹ️ For more information:

Type `/help`.
"""


