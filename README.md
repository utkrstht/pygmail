# pygmail
Python Gmail client to send emails fast and easy  
Installation through `pip install *********` (Currently not on the PyPi index.)  
  
### how to use
**first run**  
you first install using `pip install pygmail`,  
then you run `pygmail authenticate`, you choose the email from which you wish to send emails.  
pygmail will ask to be able to send emails on your behalf.  

once that's complete, a private token will be created in your home dir inside `.pygmail/`  
the exact directory will be printed as well.  

**sending emails**  
You can see examples for sending emails in `examples/` in [here](https://github.com/utkrstht/pygmail).  
pygmail can send one singular attachment, cc and bcc (per email message) and html bodies.  
this is totally a feature and not at all an issue in my code!!!!

**reading emails**
currently pygmail has no such feature, it will come soon in the future  

### common errors
`[WinError 10061] No connection could be made because the target machine actively refused it` --- The backend server is down, wait a few minutes or so.  
`500 Server Error` --- Server is under maintence, and so the server ran into an error trying to process your request.
