from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Initialize client
# Make sure you authenticated before using `pygmail authenticate` or client.authenticate()
# or that you passed the session token directly as a string like this:
# client.init("SESSION_TOKEN")
client.init()

# List recent emails
# emails['messages'] returns a dictionary, containing:
# headers (from, to, subject, etc), body_plain, body_html and attachments
# list_emails returns, messages, next_page_token and result_size_estimate (how many emails)
# Inorder to get next page results, you need to pass next_page_token to list_emails' page_token
emails = client.list_emails(max_results=30)

# Print how many emails found
print(f"Found {len(emails['messages'])} emails")

# Parse the email
message_id = emails['messages'][0]['id'] 

email = client.get_parsed_email(message_id)

attachment_id = email['attachments'][1]['attachment_id']

filename = email['attachments'][1]['filename']

# You need to supply message_id from raw email (unparsed)
# If you don't specify output path, get_attachment will return the raw bytes.
client.get_attachment(message_id=message_id, attachment_id=attachment_id, output_path=filename)

# You can download all attachments of an message
# By default, all attachments are downloaded to a folder "attachments"
# in the current working directory, You can change this by changing output_path
client.get_all_attachments(message_id=message_id, output_path=".")



