# Documentation 

### how to use

#### **authenticate**
Authenticate using `pygmail authenticate`, to be more secure, you should restrict the generated session token to only the IPs you'll be using, this way you can prevent unauthorized use:  
`pygmail authenticate --restrict <IP>`  
or, if using multiple IPs  
`pygmail authenticate --restrict "<IP>, <IP2>, <IP3>"`  

If you prefer to authenticate using python directly, see below (Read comments):  
```py
from pygmail import GmailClient

# Create pygmail instance
client = GmailClient()

# Trigger authentication, this will create a session.token file in your home dir
# that directory will be printed in the terminal

# You can restrict which IPs can use the generated session token
# by passing a list to allowed_ips:
# client.authenticate(allowed_ips=["1.2.3.4"])

# You can set if you don't want the browser link to automatically open,
# and just print the link by setting open_browser=False:
# client.authenticate(open_browser=False)

# You can increase/decrease the timeout for recieving the OAuth codes,
# by changing timeout integer in seconds (default is 300 seconds):
# client.authenticate(timeout=200)
client.authenticate()

# You can also check if you're authenticated by doing:
# client.is_authorized(), returns true if authenticated, else false.
client.is_authorized()
```

You can also fetch your own authorized account's details:
```py
client.me()
```
Response Structure:
```
response
│
└── user (Dictionary)
     ├── id (String)
     ├── email (String)
     ├── verified_email (Boolean)
     ├── name (String)
     ├── given_name (String)
     ├── family_name (String)
     └── picture (String - URL)
```

#### **sending emails**
You can send emails using pygmail, you have two options, Python or CLI.  
Python:
```py
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

# Print the message id
print(resp)
```

You can use CLI to send emails, but this is not recommended,  
You can repeat `--to`, `--cc`, `--bcc` and `--attach` flags as needed,  
Not all flags are required (only `--to` and `--subject` are required),  
If you declare `--html` and `--body`, then body will be ignored  
```bash
pygmail send \
--to <email> \
--cc <email> \
--bcc <email> \
--subject <subject> \
--body <body> \ 
--html <path to html file> \
--attach <path to attachment>
```

#### **reading emails**
You can read/search emails using pygmail,  
```py
emails = client.list_emails()
```
Response Structure:
```
response
│
├── messages[]
│     ├── id (string)
│     └── threadId (string)
│
├── next_page_token (string)
└── result_size_estimate (integer (how many email messages found for the query))
```

You need to parse an email if you wish to fetch it's data.  
After parsing a specific email using:
```py 
message_id = emails['messages'][0]['id']
email = client.get_parsed_email(message_id)
```

You get this response structure:
```
emails
│
├── headers (Dictionary)
│     ├── From (String)
│     ├── To (String)
│     ├── Subject (String)
│     └── Date (String)
│
├── body_plain (String)
├── body_html (String)
└── attachments[] (List[Dictionary])
      ├── filename (string)
      ├── mime_type (string)
      ├── attachment_id (string)
      └── size (integer)

```

To fetch any value, (e.g. size of an attachment), you can follow this:
```py
attachment_size = email['attachments'][0]['size'] # 0 is the attachment index
```
Simply follow the tree.

If you wish to access previous pages, you'll need to pass `next_page_token` to `list_emails`'s `page_token` in another request:  
```py
next_page = client.list_emails(page_token=next_page_token)
```

You can also, query/search for specific things:
```py
# Search for something
emails = client.list_emails(query="I am searching")

# Search for emails from a specific sender
emails = client.list_emails(query="from:someone@gmail.com")

# Search for unread emails
emails = client.list_emails(query="is:unread")
```
You can query anything that you can in normal gmail.
 

To set how many results/emails you can get at a time, you can set `max_results`  
You can't set it over 100 though, as gmail can only supply 100 at a time  
If you don't set it, it'll default to 10:  
```py
emails = client.list_emails(max_results=50)
```

You currently cannot download attachments, but this is being worked on.

#### **examples**
Find examples in `examples/`
- `authenticate.py` --- Authenticate using python instead of CLI with client.authenticate()  
- `me.py` --- Check which account is authenticated with client.me()  
- `read_email.py` --- Read emails with client.list_emails()  
- `send_email.py` --- Send emails with client.send_email()  

### common errors
`401 Client Error: Unauthorized for url`--- You're not authenticated, See above on how to.  
`[WinError 10061] No connection could be made because the target machine actively refused it` --- The backend server is down, wait a few minutes or so.  
`500 Server Error` --- Server is under maintence, and so the server ran into an error trying to process your request.
