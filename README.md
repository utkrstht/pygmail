# pygmail
Python Gmail client to send emails fast and easy  
Installation through `pip install pygmail`  

(being made for midnight.hackclub.com)  
The backend server is being hosted on [Nest](https://hackclub.app)
  
### how to use
#### **first run**  
you first install using `pip install pygmail`,  
then you run `pygmail authenticate`, you choose the email from which you wish to use pygmail from.

once that's complete, a private token will be created in your home dir inside `.pygmail/`  
the exact directory will be printed as well.  

#### **examples**
Find examples in `examples/`
- `authenticate.py` --- Authenticate using python instead of CLI with client.authenticate()  
- `me.py` --- Check which account is authenticated with client.me()  
- `read_email.py` --- Read emails with client.list_emails()  
- `send_email.py` --- Send emails with client.send_email()  

#### **sending emails**  
You can see examples for sending emails in `examples/` in [here](https://github.com/utkrstht/pygmail).

#### **reading emails**
You can see examples for reading emails in `examples/` in [here](https://github.com/utkrstht/pygmail).

### common errors
`401 Client Error: Unauthorized for url`--- You're not authenticated, See above on how to.  
`[WinError 10061] No connection could be made because the target machine actively refused it` --- The backend server is down, wait a few minutes or so.  
`500 Server Error` --- Server is under maintence, and so the server ran into an error trying to process your request.
