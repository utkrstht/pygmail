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
    to="someone@gmail.com",
    subject="Monkey Selfie",
    cc=["somebodyelse@gmail.com", "absolutelyhugecat@gmail.com"],
    bcc="secretperson@gmail.com",
    body="See monkey selfie",
    # If you declare html and also declare body, the body will be ignored.
    html="<h1>Selfie</h1><p>See Monkey's attached selfie</p>",
    # attachments field must always be an array
    attachments=["selfie.png"]
)

resp = client.send_email(
    to="someone@gmail.com",
    subject="Monkey Selfie",
    cc=["somebodyelse@gmail.com", "absolutelyhugecat@gmail.com"],
    bcc="secretperson@gmail.com",
    body="See monkey selfie",
    # If you declare html and also declare body, the body will be ignored.
    html="<h1>Selfie</h1><p>See Monkey's attached selfie</p>",
    # attachments field must always be an array
    attachments=["selfie.png"]
)

# To reply to a message/thread
# You can pass the thread_id to the reply argument
# You will need to specify everyone that needs to get the message
# You can pass any field that is applicable normally
resp2 = client.send_email(
    to="recipient@example.com",
    subject="This is a Subject",
    body="This is a body",
    reply="thread_id" 
)


# Print the message id
print(resp)

# Print the reply id
print(resp2)