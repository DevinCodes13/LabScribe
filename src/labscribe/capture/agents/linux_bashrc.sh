# ============================================================
# LabScribe capture agent — Linux VM (SIEM01, KALI01)
# ============================================================
# Records each interactive shell session (commands + output) into
# the LabScribe shared folder using `script`. Nothing outside the
# terminal is ever recorded.
#
# ONE-TIME INSTALL (inside the VM):
#   1. In VirtualBox, add the shared folder (Devices > Shared
#      Folders, Auto-mount). It appears as /media/sf_<ShareName>.
#      Add your user to the vboxsf group so you can write to it:
#         sudo usermod -aG vboxsf $USER   (then log out/in)
#   2. Append this whole snippet to ~/.bashrc, adjust
#      LABSCRIBE_DIR if your mount path differs.
#   3. Open a new terminal.
# ============================================================

LABSCRIBE_DIR="{{LINUX_CAPTURE_PATH}}/transcripts"

# Guards: folder reachable, interactive shell, and not already recording
# (without LABSCRIBE_ACTIVE, `script` spawning a shell would loop forever)
#
# --flush: script writes to a regular file, so without this it buffers output
# in ~4KB chunks instead of writing as you type. That makes LabScribe's live
# counts and the file itself look "stuck" for a while after real activity.
# --flush trades a little efficiency for the file staying current.
if [ -d "$LABSCRIBE_DIR" ] && [ -z "$LABSCRIBE_ACTIVE" ] && [[ $- == *i* ]]; then
    export LABSCRIBE_ACTIVE=1
    exec script -q -a --flush "$LABSCRIBE_DIR/$(date +%Y-%m-%d_%H%M)_$(hostname).txt"
fi
