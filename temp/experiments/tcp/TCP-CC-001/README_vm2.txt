=== TCP-CC-001 – VM2 receiver deployment (smoke-001) ===

PRE-REQUISITES (on VM2)
-----------------------
* A Linux system with a working C runtime (glibc) – the binary only needs libc.
* Write permission in the target directory:
      ~/experiments/tcp/TCP-CC-001/smoke-001/
* Ability to execute a binary (execute permission).

STEP-BY-STEP INSTRUCTIONS
-------------------------

1. Transfer the package (receiver binary + checksum + this README) to VM2.
   - If you have SSH/SCP from your workstation to both hosts:
        scp receiver receiver.sha256 README_vm2.txt <your-login>@<vm2-host>:~/tmp/
   - If you use another mechanism (rsync, SFTP, USB, shared NFS, etc.),
     copy the three files to any temporary location on VM2 (e.g. `~/tmp/`).

2. On VM2, verify the integrity of the binary:
        cd ~/tmp
        sha256sum -c receiver.sha256
   The output must be:
        receiver: OK

3. Create the final destination directory (if it does not already exist) and
   move the binary there:
        mkdir -p ~/experiments/tcp/TCP-CC-001/smoke-001
        mv receiver ~/experiments/tcp/TCP-CC-001/smoke-001/
        chmod +x ~/experiments/tcp/TCP-CC-001/smoke-001/receiver

4. (Optional) Keep the checksum file for future reference:
        mv receiver.sha256 ~/experiments/tcp/TCP-CC-001/smoke-001/
        mv README_vm2.txt   ~/experiments/tcp/TCP-CC-001/smoke-001/

5. Start the receiver **in the smoke-001 directory** so that its log file
   (`receiver_log.csv`) is written there:

        cd ~/experiments/tcp/TCP-CC-001/smoke-001
        ./receiver &

   The `&` runs the process in the background. Verify it started:
        ss -ltnp | grep ':5204'
   Expected example output:
        LISTEN 0      128          *:5204                     *:*      users:("receiver",pid=1234,fd=3)

6. Verify the receiver is listening and the host is correctly configured:

        hostname
        ip -4 addr show ens4
        ss -ltnp | grep ':5204'

   The `ss` line should show the receiver process attached to port 5204.

7. When you are ready to run the sender (after confirming the receiver is up),
   execute on VM1:
        /home/rosa/experiments/tcp/TCP-CC-001/sender 3

   *Do not run the sender until you explicitly confirm that the receiver is ready.*

--- End of README_vm2.txt ---