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

for msg in emails['messages']:
    print(f"Message ID: {msg['id']}")

# Get next_page_token
next_page_token = emails.get("next_page_token")
    
# Loop until all pages have been read    
while True:
    # If at last page, next_page_token will be none.
    if next_page_token == None:
        break

    # Fetch 100 emails at a time, and also pass page_token.
    emails = client.list_emails(max_results=100, page_token=next_page_token)

    # Print all message IDs
    for msg in emails['messages']:
        print(f"Message ID: {msg['id']}")
    
    # Note that we're using .get() instead of directly accessing
    # the dictionary, since if next_page_token doesn't exist, .get()
    # will return None, unlike directly accessing it, which will result in an error.
    next_page_token = emails.get("next_page_token")
