Welcome to LabScribe!

LabScribe watches you build a home cybersecurity lab (VirtualBox VMs) and
writes your GitHub documentation for you -- a README with a network diagram,
generated from what you actually did.

BEFORE YOU START, you'll need:

  1. Your own Anthropic API key (required -- LabScribe cannot generate docs
     without one). Sign up at https://console.anthropic.com and create a key.
     You enter this once in LabScribe's Settings screen. It is stored only
     on YOUR OWN machine, in a local file, and is never shared with anyone
     -- including whoever gave you this installer. Anthropic bills API
     usage to whichever key is entered, so make sure it's your own.

  2. Git (required to commit generated docs to your own GitHub repo)
     https://git-scm.com/downloads

  3. nmap -- optional, only needed for the live network-diagram scan
     https://nmap.org/download

WHAT LABSCRIBE DOES AND DOES NOT DO:

  - It reads terminal transcripts from your lab VMs, but only after you
    install a one-time capture snippet yourself -- nothing is recorded
    automatically or without your setup.
  - It reads screenshots only when you manually take them.
  - It NEVER records your screen, and NEVER captures anything outside a
    lab terminal session you've explicitly set up.
  - Nothing is ever committed to a git repo without you reviewing it first.

Click Next to continue installing LabScribe.
