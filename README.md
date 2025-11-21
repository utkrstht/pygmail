# pygmail
Python Gmail client to send emails fast and easy  
Installation through `pip install pygmail`  

> [!IMPORTANT]
> Do note that pygmail is not currently on PyPi

(being made for midnight.hackclub.com)  
The backend server is being hosted on [Nest](https://hackclub.app)
  
### how to use
#### manual installation
First, clone the repository:
```
git clone https://github.com/utkrstht/pygmail.git
```
Then, cd into the repository:
```
cd pygmail/pygmail
```
Now finally, run 
```
pip install .
```
and Done!

#### **first run**  
you first install using `pip install pygmail`,  
Authenticate using `pygmail authenticate`, to be more secure, you should restrict the generated session token to only the IPs you'll be using, this way you can prevent unauthorized use:  
`pygmail authenticate --restrict <IP>`  
or, if using multiple IPs  
`pygmail authenticate --restrict "<IP>, <IP2>, <IP3>"`

#### **documentation**
You can find documentation in `DOCUMENTATION.md` in root.

#### **examples**
Find examples in `examples/`
- `authenticate.py` --- Authenticate using python instead of CLI with authenticate()  
- `me.py` --- Check which account is authenticated with me()  
- `read_email.py` --- Read emails with list_emails()  
- `read_all_emails.py` --- Read all emails using page tokens and list_emails()
- `send_email.py` --- Send emails with send_email()  
- `get_attachment.py` --- Get attachments using get_attachment() 

### common errors
`401 Client Error: Unauthorized for url`--- You're not authenticated, See [this](#authenticate) on how to.  
`[WinError 10061] No connection could be made because the target machine actively refused it` --- The backend server is down, wait a few minutes or so.  
`500 Server Error` --- Server is under maintence, and so the server ran into an error trying to process your request.
