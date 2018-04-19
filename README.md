# Community CTFd (CCTFd)

CCTFd is a plugin made for CTFd, an open-source CTF hosting platform.

## Features

CCTFd allows any user to submit new challenges to the platform, so that they can be played by the other users without the need to ask an administrator.

* Every user can submit new challenges to the platform.
* Bonus points are given to challenge's creator when their challenge gets solved *for the first time*.
* Players can only modify, but cannot validate their own challenges.
* Markdown descriptions are supported, but HTML is being sanitized for community challenges in order to prevent XSS.

## What's missing

* CCTFd needs to modify a few templates as well as a few stylesheets. It is not very portable ; the compatibility with custom themes is thus not complete.
* Once CCTFd is installed, it is always enabled. It should be trivial to add an option to disable it and re-enable it later from the CTFd config.

Feel free to fork and contribute to this repository.

## Installation

1. Clone this repository to CTFd/plugins. Please keep the files named the same way so CTFd can serve the files in the assets directory.

2. Run CTFd. It should automatically load CCTFd.
