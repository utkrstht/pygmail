from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Initialize client
# Make sure you authenticated before using `pygmail authenticate` or client.authenticate()
# or that you passed the session token directly as a string like this:
# client.init("SESSION_TOKEN")
client.init()

# Get authenticated email info
# It will return a json object so we print it
print(client.me())