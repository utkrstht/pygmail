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
    to="meghna.tndpa@gmail.com",
    subject="Monthly Monkey Man",
    cc=["sampannthestar@gmail.com", "krishkracks@gmail.com"],
    body="See monkey selfie",
    # If you declare html and also declare body, the body will be ignored.
    html="<h1>Selfie</h1><p>See matto's attached selfie</p>",
    # attachments field must always be an array and it only accepts one attachment for now
)

# Print the message id
print(resp)