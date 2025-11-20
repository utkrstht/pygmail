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