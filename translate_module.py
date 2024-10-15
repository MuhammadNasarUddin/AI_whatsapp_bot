from deep_translator import GoogleTranslator

def translate_text(text, dest='en'):
    translated_text = GoogleTranslator(source='auto', target=dest).translate(text)
    return translated_text


