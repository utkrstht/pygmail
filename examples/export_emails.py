from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Initialize client
# Make sure you authenticated before using `pygmail authenticate` or client.authenticate()
# or that you passed the session token directly as a string like this:
# client.init("SESSION_TOKEN")
client.init()

emails = client.list_emails()

message_ids = [msg['id'] for msg in emails['messages']]

# Export
client.export_emails(target=message_ids, output_file="selected_emails.csv")