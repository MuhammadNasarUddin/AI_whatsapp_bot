import stripe
import mysql.connector
import logging
from twilio.rest import Client
import os
from dotenv import load_dotenv


load_dotenv()



stripe.api_key = ""

# Twilio credentials (replace with your actual credentials)
account_sid = os.getenv('twilio_account_sid')
auth_token = os.getenv('twilio_auth_token')
twilio_number = os.getenv('twilio_whatsapp_number')

client = Client(account_sid, auth_token)


def generate_payment_url(package, user_id):
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host='',
            user='',
            password='',
            database='',
        )
        cursor = conn.cursor()

        if package == 'unlimited_10':
            amount = 10.00
            amount_cents = int(amount * 100)
            description = "Unlimited Monthly Subscription"

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': "Unlimited Package",
                        'description': description,
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'',
            cancel_url='',
        )

        return session.url

    except Exception as e:
        logging.error(f"An error occurred while generating payment URL: {str(e)}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()








def handle_successful_payment(user_id, package):
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host='',
            user='',
            password='',
            database='',
        )
        cursor = conn.cursor()

        cursor.execute("SELECT user_id, phone_number, tokens FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if user:
            if package == 'unlimited_10':
                new_tokens = 999999999  # Store a very large number to represent "unlimited" tokens

            # Update the user's token count in the database
            cursor.execute("UPDATE users SET tokens = %s WHERE user_id = %s", (new_tokens, user_id))
            conn.commit()
            logging.info(f"Tokens updated successfully. New tokens: {new_tokens}")

            # Send WhatsApp message to the user
            client.messages.create(
                body=f"Payment successful! You now have unlimited access.",
                from_=twilio_number,
                to=user[1]
            )

            return new_tokens  # Return the new token balance
        else:
            logging.error("User not found in the database.")
            return None

    except Exception as e:
        logging.error(f"Error updating tokens: {str(e)}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
