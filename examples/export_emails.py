from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Initialize client
# Make sure you authenticated before using `pygmail authenticate` or client.authenticate()
# or that you passed the session token directly as a string like this:
# client.init("SESSION_TOKEN")
client.init()

emails = client.list_emails()

# Placeholder for message_ids
messageid=[]

# Loop through all emails and add all ids to list
for msg in emails['messages']:
    messageid.append(msg['id'])

# Export
client.export_emails(target=messageid, output_file="selected_emails.csv")