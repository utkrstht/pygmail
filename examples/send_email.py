from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Initialize client
# Make sure you authenticated before using `pygmail authenticate` or client.authenticate()
# or that you passed the session token directly as a string like this:
# client.init("SESSION_TOKEN")
client.init()

# Now send the email
resp = client.send_email(
    to="krishkracks@gmail.com",
    subject="Monkey Selfie",
    cc=["sampannthestar@gmail.com", "meghna.tndpa@gmail.com"],
    body="See monkey selfie",
    # If you declare html and also declare body, the body will be ignored.
    html="<h1>Selfie</h1><p>See Monkey's attached selfie</p>",
    # attachments field must always be an array
)

# Print the message id
print(resp)