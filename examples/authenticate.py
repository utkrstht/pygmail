from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Trigger authentication, this will create a session.token file in your home dir
# that directory will be printed in the terminal
client.authenticate()