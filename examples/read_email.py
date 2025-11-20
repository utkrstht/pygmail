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

for msg in emails['messages']:
    print(f"Message ID: {msg['id']}")

# Get a specific email (parsed and readable)
if emails['messages']:
    # Get latest email
    message_id = emails['messages'][0]['id']
    email = client.get_parsed_email(message_id)
    
    print(f"From: {email['headers'].get('From')}")
    print(f"Subject: {email['headers'].get('Subject')}")
    print(f"Date: {email['headers'].get('Date')}")
    print(f"\nBody:\n{email['body_plain']}")

    # Check if the email has attachments
    # emails['attachments'] has these subdictionaries:
    # filename, mime_type, attachment_id and size (in bytes)
    if email['attachments']:
        print(f"\nAttachments: {len(email['attachments'])}")
        for att in email['attachments']:
            print(f"  - {att['filename']} ({att['mime_type']})")

# Search for specific emails
unread = client.list_emails(query="is:unread")
print(f"Unread emails: {len(unread['messages'])}")

# Search by sender
from_specific = client.list_emails(query="from:sender@gmail.com")


if from_specific['messages']:
    # Print how many messages from specific person
    print(f"Found {len(from_specific['messages'])} emails")

    # Get latest email
    message_id = from_specific['messages'][0]['id']
    email = client.get_parsed_email(message_id)
    
    print(f"From: {email['headers'].get('From')}")
    print(f"Subject: {email['headers'].get('Subject')}")
    print(f"Date: {email['headers'].get('Date')}")
    print(f"\nBody:\n{email['body_plain']}")
    
    if email['attachments']:
        print(f"\nAttachments: {len(email['attachments'])}")
        for att in email['attachments']:
            print(f"  - {att['filename']} ({att['mime_type']})")