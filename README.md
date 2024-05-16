A Terminal-based Search Server
==============================


The telnet.py server is, well... for telnet clients. 

Install PyPDF2 with:
<pre>pip3 install PyPDF2</pre>

The SSH server in Python
========================

You will need to pip install paramiko. 


The SSH server requires you to set up a key like this:
<pre>
  ssh-keygen -t rsa -f server_key -N ''

</pre><br>
Then, start the server. 
Connect to the server using an SSH client (e.g., ssh username@localhost -p 8023). Any username and password will be accepted for simplicity.


The SSH server in Go
====================

The SSH server requires you to set up a key like this:
<pre>
  ssh-keygen -t rsa -f server_key -N ''

</pre><br>
  
  
To build do:
<pre>
  go mod init ssh
  go mod tidy
  go build ssh.go
</pre>


How to make it work with searchable content
===========================================

Create a subdirectory FILES/ and put all the text files you want to search in that subdirectory.   
  
Moshix, May, 2024
Munich, Germany
